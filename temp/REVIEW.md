---
phase: code-review
reviewed: 2026-05-17T00:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - backend/cmd/server/main.go
  - backend/internal/config/config.go
  - backend/internal/console/handler.go
  - backend/internal/console/templates.go
  - backend/internal/fabquery/engine.go
  - backend/internal/fabquery/rownum.go
  - backend/internal/fabquery/sse.go
  - backend/internal/fabquery/testdb.go
  - backend/internal/fabquery/validator.go
  - backend/tests/console/handler_test.go
  - backend/tests/fabquery/engine_test.go
  - sidecar/main.py
  - backend/Dockerfile
findings:
  critical: 5
  warning: 7
  info: 3
  total: 15
status: issues_found
---

# Code Review Report

**Reviewed:** 2026-05-17  
**Depth:** standard  
**Files Reviewed:** 13  
**Status:** issues_found

## Summary

Reviewed a Go backend (chi router, SSE streaming, multi-fab fan-out) plus a Python FastAPI sidecar that proxies Oracle queries. The codebase has a reasonably clean structure, but contains several high-severity defects: the SQL validator can be trivially bypassed to allow DDL/DML execution on production databases; the query store leaks memory without bounds; HTTP request/response decode errors are silently swallowed; the SSE stream does not propagate context cancellation to in-flight goroutines; and the sidecar leaks Oracle connections on errors. There are also a cluster of warnings around missing fab validation, wildcard CORS on the SSE endpoint, and a mutable default argument in Python.

---

## Critical Issues

### CR-01: SQL Validator Can Be Bypassed — DDL/DML Executes on Production Fabs

**File:** `backend/internal/fabquery/validator.go:11-16`  
**Issue:** `ValidateSelectOnly` only checks whether the uppercased, trimmed SQL *starts with* `SELECT` or `WITH`. An attacker can embed arbitrary DDL or DML after a leading SELECT/WITH keyword that is structurally valid to the prefix check but changes behaviour. More practically, Oracle supports `SELECT ... INTO` (PL/SQL), `WITH ... INSERT` (12c+), and -- most dangerously -- a user can pass a SQL statement with an embedded comment or semicolon to chain statements in some driver configurations (e.g. `SELECT 1 FROM dual; DROP TABLE users`). Prefix matching on uppercased text is also defeated by Unicode normalisation edge cases (`ｓｅｌｅｃｔ` uppercases to `SELECT` in some locales). The validator approves any string that begins with "WITH", which includes `WITH cte AS (DELETE ... RETURNING ...)` on Oracle 23c.

**Fix:** At minimum, after the prefix check, scan the entire statement for disallowed keywords (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, MERGE, EXECUTE, CALL, GRANT, REVOKE). Since a full parser is impractical, use a token-boundary regex rather than substring matching so `SELECTS` is not accepted:

```go
import "regexp"

var (
    allowedPrefix = regexp.MustCompile(`(?i)^\s*(SELECT|WITH)\s`)
    dmlKeyword    = regexp.MustCompile(`(?i)\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|MERGE|EXECUTE|CALL|GRANT|REVOKE)\b`)
)

func ValidateSelectOnly(sql string) error {
    if !allowedPrefix.MatchString(sql) {
        return fmt.Errorf("only SELECT queries are allowed")
    }
    if dmlKeyword.MatchString(sql) {
        return fmt.Errorf("only SELECT queries are allowed")
    }
    return nil
}
```

---

### CR-02: Request-Supplied Fab List Is Never Validated Against Known Fabs

**File:** `backend/internal/console/handler.go:79-82`  
**Issue:** The handler checks `len(req.Fabs) == 0` but never checks whether each fab name in the request is in `config.ValidFabs`. Any arbitrary string is accepted and stored. Because `engine.queryFab` constructs a URL as `url + "/query"` where `url` is looked up by fab name, an unknown fab simply returns an error result — but `config.ValidFabs` is defined precisely to enumerate the allowed fab identifiers. Allowing arbitrary fab names means the stored query object can contain attacker-controlled strings which are then compared against internal maps, and also means that error messages may leak internal sidecar URL topology.

**Fix:** Validate each fab name against `config.ValidFabs` in the handler before proceeding:

```go
import "isop-cpnt/backend/internal/config"

validFabSet := make(map[string]struct{}, len(config.ValidFabs))
for _, f := range config.ValidFabs {
    validFabSet[f] = struct{}{}
}

for _, fab := range req.Fabs {
    if _, ok := validFabSet[fab]; !ok {
        writeJSON(w, 400, errorResponse{fmt.Sprintf("unknown fab: %s", fab)})
        return
    }
}
```

---

### CR-03: Query Store Grows Without Bound — Unbounded Memory Leak

**File:** `backend/internal/console/handler.go:99-104`  
**Issue:** Every call to `Execute` stores a `storedQuery` in `h.store` (a `sync.Map`) with a 5-minute TTL. The expiry is only checked lazily in `Stream` and entries are only deleted on access. If `Stream` is never called for a query ID (e.g., client drops connection, or in a DoS scenario), the entry is never removed. A steady stream of `POST /api/fabs/query` requests will grow the sync.Map indefinitely, consuming memory proportional to the number of unanswered queries. Since `queryID` is a UUID and the SQL + rows are stored inline, each entry can be substantial.

**Fix:** Start a background goroutine in `NewHandler` (or in `main`) that periodically sweeps expired entries:

```go
func (h *Handler) startCleanup(interval time.Duration) {
    go func() {
        ticker := time.NewTicker(interval)
        defer ticker.Stop()
        for range ticker.C {
            h.store.Range(func(k, v interface{}) bool {
                if q, ok := v.(storedQuery); ok && time.Now().After(q.expiresAt) {
                    h.store.Delete(k)
                }
                return true
            })
        }
    }()
}
```

Call `h.startCleanup(time.Minute)` in `NewHandler`.

---

### CR-04: HTTP Request Construction Error Silently Ignored — Potential Nil Pointer Panic

**File:** `backend/internal/fabquery/engine.go:60` and `backend/internal/fabquery/testdb.go:30`  
**Issue:** Both files use the blank-identifier pattern `req, _ := http.NewRequestWithContext(...)` and then immediately dereference `req` (`req.Header.Set(...)`). `http.NewRequestWithContext` returns an error when the URL is invalid or the method is invalid; in that case `req` is `nil`. Calling `nil.Header.Set(...)` panics. In practice the method is a constant, but `url` is read from environment variables and could be malformed (e.g., missing scheme). The `Recoverer` middleware will catch the panic at the HTTP handler boundary, but for `testdb.go` the panic propagates inside `TryRun` through the HTTP handler stack.

**Fix:** Handle the error explicitly in both locations:

```go
req, err := http.NewRequestWithContext(ctx, http.MethodPost, url+"/query", bytes.NewReader(body))
if err != nil {
    return FabResult{Fab: fab, Status: "error", Error: fmt.Sprintf("build request: %v", err)}
}
```

---

### CR-05: Oracle Connection Leaked in Sidecar on cursor.description Access Failure

**File:** `sidecar/main.py:33-43`  
**Issue:** The `try/finally` block in `query()` calls `_pool.release(conn)` in `finally`, which is correct for `cx_Oracle.DatabaseError`. However, `cursor.description` is `None` for DML statements that return no result set. If the SQL validator somehow allows a non-SELECT (see CR-01), `cursor.description` is `None` and the list comprehension `[col[0].lower() for col in cursor.description]` raises `TypeError`, which is **not** a `cx_Oracle.DatabaseError`. This `TypeError` is not caught by the `except` clause, bypasses the `HTTPException` raising, and propagates as an unhandled 500 — but the `finally` block does still run, so the connection is returned. The real risk: once the upstream SQL validator is bypassed (CR-01), a DML statement succeeds against the Oracle DB, and the sidecar returns a 500 error instead of the mutation being flagged. Defence-in-depth fix: add a guard.

Additionally, `cursor` is never explicitly closed before `conn` is released, leaving it to garbage collection. This can exhaust Oracle's open-cursor quota under load.

**Fix:**

```python
try:
    cursor = conn.cursor()
    try:
        cursor.execute(req.sql, req.params)
        if cursor.description is None:
            raise HTTPException(status_code=400, detail="query returned no result set")
        columns = [col[0].lower() for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return {"columns": columns, "rows": rows}
    except cx_Oracle.DatabaseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cursor.close()
finally:
    _pool.release(conn)
```

---

## Warnings

### WR-01: SSE Stream Does Not Cancel In-Flight Goroutines on Client Disconnect

**File:** `backend/internal/console/handler.go:148-159`  
**Issue:** `h.engine.Execute(r.Context(), ...)` correctly passes `r.Context()` to each goroutine, which should respect cancellation. However, the `Stream` handler blocks on `for result := range resultCh` with no select on `r.Context().Done()`. If the client disconnects, `r.Context()` is cancelled, which will cause in-flight HTTP calls inside goroutines to return errors — but the goroutines continue to run through their `defer wg.Done()` path, attempting to send on `ch`. Because `ch` is buffered to `len(fabs)`, sends will not block; this is acceptable. The actual problem is that the SSE `for range resultCh` loop has no mechanism to detect that the client is gone and stop draining the channel. SSE writes after disconnect silently fail (no error returned by `fmt.Fprintf` to a closed connection on most platforms), so behaviour is technically correct but wasteful. No goroutine leak exists because the channel will be closed. This is a robustness/clarity warning.

**Fix:** Add explicit context awareness:

```go
for {
    select {
    case result, ok := <-resultCh:
        if !ok {
            fabquery.WriteSSEEvent(w, "done", map[string]string{"status": "complete"})
            return
        }
        // ... existing event writing
    case <-r.Context().Done():
        return
    }
}
```

---

### WR-02: Wildcard CORS on SSE Endpoint Leaks Query Results Cross-Origin

**File:** `backend/internal/fabquery/sse.go:24`  
**Issue:** `SetSSEHeaders` unconditionally sets `Access-Control-Allow-Origin: *`. For a SQL console serving potentially sensitive fab data, wildcard CORS means any web page on any domain can initiate a GET to `/api/fabs/stream/{id}` and read the SSE response. Although the query ID is a UUID, UUIDs are not a security primitive (they provide no authentication). If a user is tricked into visiting a malicious page while authenticated (or if there is no authentication layer upstream), query results are exposed cross-origin.

**Fix:** Restrict CORS to the known console origin, or gate it via an environment variable. Remove the header from `SetSSEHeaders` and handle it in a proper CORS middleware (e.g., `github.com/go-chi/cors`) configured with allowed origins.

---

### WR-03: `json.NewDecoder(...).Decode(...)` Errors Silently Ignored

**File:** `backend/internal/fabquery/engine.go:74` and `backend/internal/fabquery/testdb.go:46`  
**Issue:** Decoding errors from the sidecar response body are discarded. In `engine.go:74`, if decoding fails (malformed JSON, network truncation), `payload` remains zero-valued: `payload.Detail` is `""` and `payload.Columns`/`payload.Rows` are nil. For a non-200 response this means the `FabResult.Error` field is `""` — the caller gets an error status with no message. For a 200 response with a malformed body, the result appears successful with no columns and no rows, silently returning empty data instead of surfacing the error.

**Fix:**

```go
if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
    return FabResult{Fab: fab, Status: "error", Error: fmt.Sprintf("decode response: %v", err)}
}
```

---

### WR-04: Mutable Default Argument in Pydantic Model

**File:** `sidecar/main.py:28`  
**Issue:** `params: dict = {}` is a mutable default argument on a Pydantic `BaseModel`. While Pydantic internally copies model defaults for each instance, using a bare mutable literal (`{}`) is not idiomatic and can cause issues if the Pydantic version handling changes or if the model is used in non-standard ways. The correct pattern for optional dict fields in Pydantic is `Field(default_factory=dict)`.

**Fix:**

```python
from pydantic import BaseModel, Field

class QueryRequest(BaseModel):
    sql: str
    params: dict = Field(default_factory=dict)
```

---

### WR-05: `json.Marshal` Error Silently Ignored When Building Request Body

**File:** `backend/internal/fabquery/engine.go:59` and `backend/internal/fabquery/testdb.go:25`  
**Issue:** `body, _ := json.Marshal(...)` discards the error. If marshalling fails (e.g., `params` contains a value type that cannot be marshalled, such as a channel or function), `body` is `nil`. `bytes.NewReader(nil)` is valid (empty reader), so the HTTP request is sent with an empty body — the sidecar silently receives no SQL and likely returns an error or empty result. The root cause (the bad param value) is invisible in logs.

**Fix:**

```go
body, err := json.Marshal(map[string]interface{}{"sql": sql, "params": params})
if err != nil {
    return FabResult{Fab: fab, Status: "error", Error: fmt.Sprintf("marshal request: %v", err)}
}
```

---

### WR-06: No Rate Limiting or Authentication on Query Endpoint

**File:** `backend/cmd/server/main.go:40-42`  
**Issue:** The three API routes (`/api/fabs/query`, `/api/fabs/stream/{id}`, `/api/console/templates`) have no authentication or rate-limiting middleware. Any caller that can reach the server can submit arbitrary SQL to every configured fab, consuming Oracle connection pool slots and sidecar compute. Combined with CR-01 (validator bypass), this is directly exploitable. Even with a fixed validator, an unauthenticated caller can saturate the pool and block legitimate users.

**Fix:** Add at minimum a rate-limiting middleware (e.g., `golang.org/x/time/rate` or a chi-compatible package). If this service is internal-only, document the network-level access controls explicitly and add an IP allowlist middleware. If external, add token-based authentication.

---

### WR-07: `storedQuery` Reuse After Stream Is Not Prevented — Repeated Streaming Allowed

**File:** `backend/internal/console/handler.go:134-144`  
**Issue:** After a successful `Stream` call, the query entry is not deleted from `h.store`. Within the 5-minute TTL window, the same `queryID` can be streamed multiple times. Depending on the threat model, this allows an attacker who intercepts or guesses a UUID to replay the query fan-out, creating load on all sidecar instances repeatedly. It also means the in-flight goroutines from a previous stream call may still be running when a second stream call starts on the same channel — except the channel is re-created in `Execute`, so there is no channel aliasing bug, but the intent is likely single-use.

**Fix:** Delete the store entry immediately after loading it in `Stream`:

```go
val, ok := h.store.Load(queryID)
if !ok { ... }
h.store.Delete(queryID) // consume query, prevent replay
q := val.(storedQuery)
```

---

## Info

### IN-01: Dockerfile Runs Container as Root

**File:** `backend/Dockerfile:11-22`  
**Issue:** The final image has no `USER` directive; the container process runs as `root`. This violates container least-privilege principles: if a vulnerability allows container escape, the attacker has root on the host.

**Fix:** Add a non-root user in the final stage:

```dockerfile
RUN addgroup -S app && adduser -S app -G app
USER app
```

---

### IN-02: `LoadTemplates` Uses Relative Path — Runtime Working Directory Dependency

**File:** `backend/cmd/server/main.go:29`  
**Issue:** `console.LoadTemplates("config/context_sqls.yaml")` uses a relative path. If the binary is started from a directory other than `/app` (e.g., during local development or in a different deployment layout), the template load fails fatally at startup. The Dockerfile copies the binary and config to `/app` and the default `CMD` starts from there, so it works in Docker — but it is fragile.

**Fix:** Accept the config path via an environment variable or flag so it can be overridden without rebuilding:

```go
cfgPath := envOr("CONTEXT_SQLS_PATH", "config/context_sqls.yaml")
templates, err := console.LoadTemplates(cfgPath)
```

---

### IN-03: `TestStream_SendsSSEEvents` Does Not Assert Event Content Correctness

**File:** `backend/tests/console/handler_test.go:126-132`  
**Issue:** The test asserts that the body contains the substrings `"fab_result"` and `"done"`, but does not verify that the JSON payload within `fab_result` is well-formed or contains the expected columns/rows from the mock sidecar. A regression that corrupts the SSE data field would not be caught.

**Fix:** Parse the SSE lines and decode the `data:` JSON payload to verify `columns` and `rows` are present and correctly structured.

---

_Reviewed: 2026-05-17_  
_Reviewer: Claude (gsd-code-reviewer)_  
_Depth: standard_
