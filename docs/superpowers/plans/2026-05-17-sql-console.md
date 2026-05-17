# SQL Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the SQL Console feature end-to-end — multi-fab plain SQL query interface with SSE streaming, context SQL templates, diff visualization, and pivot view.

**Architecture:** Angular 21 (Signals + Monaco Editor) sends SQL to Go backend which validates (SELECT-only), wraps ROWNUM, trial-runs on Test DB sidecar, then fans out goroutines per Fab via a shared `/internal/fabquery` engine, streaming results back via SSE. Frontend accumulates results into signals and computes diff/pivot client-side.

**Tech Stack:** Angular 21 (standalone, Signals), `@monaco-editor/angular`, Go 1.22+, `chi` router, `google/uuid`, Python 3.11+, FastAPI, cx_Oracle, Docker Compose

---

## File Map

```
backend/
  cmd/server/main.go                  ← HTTP server entrypoint, route wiring
  go.mod
  config/
    context_sqls.yaml                 ← context SQL templates config
  internal/
    config/
      config.go                       ← AppConfig (fab→sidecar URL map, fab list)
    fabquery/
      validator.go + _test.go         ← SELECT-only check (prefix strategy)
      rownum.go    + _test.go         ← ROWNUM wrap
      testdb.go    + _test.go         ← Test DB trial run (5s timeout)
      engine.go    + _test.go         ← goroutine fan-out per Fab
      sse.go                          ← SSE event writer helper
    console/
      handler.go   + _test.go         ← POST /api/fabs/query + GET /api/fabs/stream/{id}
      templates.go + _test.go         ← context_sqls.yaml loader

sidecar/
  main.py                             ← FastAPI app (POST /query, GET /health)
  requirements.txt
  tests/test_main.py

frontend/
  src/app/
    models/
      fab-query.models.ts             ← TypeScript interfaces + detectDiff()
    services/
      fab-query.service.ts            ← FabQueryService (SSE client)
    shared/
      fab-selector/
        fab-selector.component.ts + .html
        fab-selector.component.spec.ts
      results/
        results.component.ts + .html
        flat-table.component.ts + .html
        diff-panel.component.ts + .html
        pivot-view.component.ts + .html
        fab-status-chip.component.ts + .html
    sql-console/
      sql-console.component.ts + .html
      context-sql/
        context-sql.component.ts + .html
        context-sql.service.ts
      sql-editor/
        sql-editor.component.ts + .html
        named-param.directive.ts + .spec.ts
    app.routes.ts
```

---

## Task 1: Monorepo Structure + Sidecar Skeleton

**Files:**
- Create: `backend/go.mod`
- Create: `sidecar/requirements.txt`
- Create: `sidecar/main.py`
- Create: `docker-compose.yml`
- Create: `.env.example`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p backend/cmd/server backend/internal/fabquery backend/internal/console backend/internal/config backend/config
mkdir -p sidecar/tests
mkdir -p frontend
```

- [ ] **Step 2: Initialize Go module**

```bash
cd backend && go mod init isop-cpnt/backend
go get github.com/go-chi/chi/v5
go get github.com/google/uuid
go get gopkg.in/yaml.v3
cd ..
```

- [ ] **Step 3: Create sidecar `requirements.txt`**

```
fastapi==0.111.0
uvicorn==0.30.0
cx_Oracle==8.3.0
pydantic==2.7.0
pytest==8.2.0
httpx==0.27.0
```

- [ ] **Step 4: Create sidecar `main.py`**

```python
import os
import cx_Oracle
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager

app = FastAPI()
_pool: cx_Oracle.SessionPool | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    _pool = cx_Oracle.SessionPool(
        user=os.environ["ORACLE_USER"],
        password=os.environ["ORACLE_PASSWORD"],
        dsn=os.environ["ORACLE_DSN"],
        min=1, max=5, increment=1,
    )
    yield
    _pool.close()

app = FastAPI(lifespan=lifespan)


class QueryRequest(BaseModel):
    sql: str
    params: dict = {}


@app.post("/query")
def query(req: QueryRequest):
    conn = _pool.acquire()
    try:
        cursor = conn.cursor()
        cursor.execute(req.sql, req.params)
        columns = [col[0].lower() for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return {"columns": columns, "rows": rows}
    except cx_Oracle.DatabaseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        _pool.release(conn)


@app.get("/health")
def health():
    try:
        conn = _pool.acquire()
        _pool.release(conn)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
```

- [ ] **Step 5: Create `.env.example`**

```
# Oracle (per-fab sidecar uses same var names, different values)
ORACLE_USER=isop_readonly
ORACLE_PASSWORD=changeme
ORACLE_DSN=dbhost:1521/ISOPDB

# Sidecar ports (prod uses K8s service names, local uses localhost)
SIDECAR_F12A_URL=http://sidecar-f12a:8000
SIDECAR_TEST_URL=http://sidecar-test:8000
```

- [ ] **Step 6: Create `docker-compose.yml` skeleton**

```yaml
version: "3.9"
services:
  backend:
    build: ./backend
    ports: ["8080:8080"]
    env_file: .env
    depends_on: [sidecar-test]

  sidecar-test:
    build: ./sidecar
    environment:
      ORACLE_USER: ${ORACLE_USER}
      ORACLE_PASSWORD: ${ORACLE_PASSWORD}
      ORACLE_DSN: ${ORACLE_TEST_DSN}
    ports: ["8001:8000"]

  frontend:
    build: ./frontend
    ports: ["4200:80"]
    depends_on: [backend]
```

- [ ] **Step 7: Commit**

```bash
git add backend/go.mod sidecar/ docker-compose.yml .env.example
git commit -m "feat: monorepo scaffold — sidecar, backend go.mod, docker-compose"
```

---

## Task 2: Sidecar Tests

**Files:**
- Create: `sidecar/tests/test_main.py`

- [ ] **Step 1: Write tests with TestClient (no real Oracle needed)**

```python
# sidecar/tests/test_main.py
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Patch cx_Oracle before importing main
mock_pool = MagicMock()
mock_conn = MagicMock()
mock_cursor = MagicMock()
mock_pool.acquire.return_value = mock_conn
mock_conn.cursor.return_value = mock_cursor

with patch.dict("sys.modules", {"cx_Oracle": MagicMock(SessionPool=MagicMock(return_value=mock_pool))}):
    from main import app  # noqa: E402

client = TestClient(app)


def test_query_returns_rows():
    mock_cursor.description = [("NAME",), ("STATUS",)]
    mock_cursor.fetchall.return_value = [("cpnt_a", "ACTIVE"), ("cpnt_b", "INACTIVE")]

    resp = client.post("/query", json={"sql": "SELECT name, status FROM cpnt", "params": {}})

    assert resp.status_code == 200
    data = resp.json()
    assert data["columns"] == ["name", "status"]
    assert data["rows"][0] == {"name": "cpnt_a", "status": "ACTIVE"}


def test_query_db_error_returns_400():
    import cx_Oracle as mock_cx
    mock_cursor.execute.side_effect = mock_cx.DatabaseError("ORA-00942: table or view does not exist")

    resp = client.post("/query", json={"sql": "SELECT * FROM no_such_table", "params": {}})

    assert resp.status_code == 400
    mock_cursor.execute.side_effect = None  # reset


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 2: Run tests**

```bash
cd sidecar && pip install -r requirements.txt && pytest tests/ -v
```

Expected: 3 passed

- [ ] **Step 3: Commit**

```bash
git add sidecar/tests/
git commit -m "test: sidecar unit tests with mocked Oracle pool"
```

---

## Task 3: Go Backend Skeleton + Config

**Files:**
- Create: `backend/internal/config/config.go`
- Create: `backend/cmd/server/main.go`

- [ ] **Step 1: Write `internal/config/config.go`**

```go
package config

var ValidFabs = []string{
    "F12A", "F12B", "F14A", "F14B", "F15A", "F15B",
    "F16", "F18A", "F18B", "F21", "F22", "F23", "APOD", "SOIC",
}

type AppConfig struct {
    SidecarURLs map[string]string // fab -> http://host:port
    TestDBURL   string
    Port        string
}

func FromEnv() AppConfig {
    urls := make(map[string]string)
    for _, fab := range ValidFabs {
        key := "SIDECAR_" + fab + "_URL"
        urls[fab] = envOr(key, "http://localhost:8000")
    }
    return AppConfig{
        SidecarURLs: urls,
        TestDBURL:   envOr("SIDECAR_TEST_URL", "http://localhost:8001"),
        Port:        envOr("PORT", "8080"),
    }
}

func envOr(key, fallback string) string {
    if v := os.Getenv(key); v != "" {
        return v
    }
    return fallback
}
```

Add `import "os"` at the top.

- [ ] **Step 2: Write `cmd/server/main.go`**

```go
package main

import (
    "log"
    "net/http"

    "github.com/go-chi/chi/v5"
    "github.com/go-chi/chi/v5/middleware"
    "isop-cpnt/backend/internal/config"
    "isop-cpnt/backend/internal/console"
    "isop-cpnt/backend/internal/fabquery"
)

func main() {
    cfg := config.FromEnv()

    engine := fabquery.NewEngine(cfg.SidecarURLs, 30)
    testDB := fabquery.NewTestDBClient(cfg.TestDBURL, 5)
    templates, err := console.LoadTemplates("config/context_sqls.yaml")
    if err != nil {
        log.Fatalf("failed to load context SQL templates: %v", err)
    }

    h := console.NewHandler(engine, testDB, templates)

    r := chi.NewRouter()
    r.Use(middleware.Logger)
    r.Use(middleware.Recoverer)

    r.Post("/api/fabs/query", h.Execute)
    r.Get("/api/fabs/stream/{id}", h.Stream)
    r.Get("/api/console/templates", h.Templates)

    log.Printf("listening on :%s", cfg.Port)
    log.Fatal(http.ListenAndServe(":"+cfg.Port, r))
}
```

- [ ] **Step 3: Verify compilation (stubs not yet written — expect import errors, that's OK)**

```bash
cd backend && go build ./... 2>&1 | head -20
```

Expected: errors about missing packages (console, fabquery) — confirm the skeleton compiles once stubs are in place.

- [ ] **Step 4: Commit**

```bash
git add backend/internal/config/ backend/cmd/
git commit -m "feat: go backend skeleton — config, main entrypoint, chi router"
```

---

## Task 4: `validator.go` — SELECT-Only Check

**Files:**
- Create: `backend/internal/fabquery/validator.go`
- Create: `backend/internal/fabquery/validator_test.go`

- [ ] **Step 1: Write the failing test**

```go
// backend/internal/fabquery/validator_test.go
package fabquery_test

import (
    "testing"
    "isop-cpnt/backend/internal/fabquery"
)

func TestValidateSelectOnly(t *testing.T) {
    cases := []struct {
        sql   string
        valid bool
    }{
        {"SELECT * FROM cpnt", true},
        {"select name from sop WHERE id = :id", true},
        {"WITH cte AS (SELECT 1 FROM dual) SELECT * FROM cte", true},
        {"  \n  SELECT col FROM tbl", true}, // leading whitespace
        {"INSERT INTO cpnt VALUES (1)", false},
        {"UPDATE cpnt SET name = 'x'", false},
        {"DELETE FROM cpnt", false},
        {"DROP TABLE cpnt", false},
        {"CREATE TABLE x (id NUMBER)", false},
        {"MERGE INTO t USING s ON (t.id=s.id) WHEN MATCHED THEN UPDATE SET t.v=s.v", false},
    }
    for _, c := range cases {
        err := fabquery.ValidateSelectOnly(c.sql)
        if c.valid && err != nil {
            t.Errorf("expected valid for %q, got: %v", c.sql, err)
        }
        if !c.valid && err == nil {
            t.Errorf("expected invalid for %q, got nil error", c.sql)
        }
    }
}
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && go test ./internal/fabquery/ -run TestValidateSelectOnly -v
```

Expected: compilation error (validator.go missing)

- [ ] **Step 3: Write minimal implementation**

```go
// backend/internal/fabquery/validator.go
package fabquery

import (
    "fmt"
    "strings"
)

// ValidateSelectOnly rejects non-SELECT statements.
// Uses prefix matching instead of a SQL parser to avoid Oracle-specific syntax incompatibilities.
func ValidateSelectOnly(sql string) error {
    upper := strings.TrimSpace(strings.ToUpper(sql))
    if strings.HasPrefix(upper, "SELECT") || strings.HasPrefix(upper, "WITH") {
        return nil
    }
    return fmt.Errorf("only SELECT queries are allowed")
}
```

- [ ] **Step 4: Run tests**

```bash
cd backend && go test ./internal/fabquery/ -run TestValidateSelectOnly -v
```

Expected: 10 cases PASS

- [ ] **Step 5: Commit**

```bash
git add backend/internal/fabquery/validator.go backend/internal/fabquery/validator_test.go
git commit -m "feat: SELECT-only validator with prefix strategy"
```

---

## Task 5: `rownum.go` — ROWNUM Auto-Wrap

**Files:**
- Create: `backend/internal/fabquery/rownum.go`
- Create: `backend/internal/fabquery/rownum_test.go`

- [ ] **Step 1: Write the failing test**

```go
// backend/internal/fabquery/rownum_test.go
package fabquery_test

import (
    "strings"
    "testing"
    "isop-cpnt/backend/internal/fabquery"
)

func TestWrapWithRownum(t *testing.T) {
    sql := "SELECT name FROM cpnt"
    wrapped := fabquery.WrapWithRownum(sql, 100)

    if !strings.Contains(wrapped, "WHERE ROWNUM <= 100") {
        t.Errorf("missing ROWNUM clause, got: %s", wrapped)
    }
    if !strings.Contains(wrapped, "SELECT name FROM cpnt") {
        t.Errorf("original SQL missing from wrap, got: %s", wrapped)
    }
    // Outer SELECT must wrap the inner
    if !strings.HasPrefix(strings.TrimSpace(wrapped), "SELECT * FROM") {
        t.Errorf("wrapped SQL should start with SELECT * FROM, got: %s", wrapped)
    }
}

func TestWrapWithRownumLimit(t *testing.T) {
    wrapped := fabquery.WrapWithRownum("SELECT 1 FROM dual", 42)
    if !strings.Contains(wrapped, "ROWNUM <= 42") {
        t.Errorf("expected limit 42, got: %s", wrapped)
    }
}
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && go test ./internal/fabquery/ -run TestWrap -v
```

Expected: compilation error

- [ ] **Step 3: Write implementation**

```go
// backend/internal/fabquery/rownum.go
package fabquery

import "fmt"

func WrapWithRownum(sql string, limit int) string {
    return fmt.Sprintf("SELECT * FROM (\n  %s\n) WHERE ROWNUM <= %d", sql, limit)
}
```

- [ ] **Step 4: Run tests**

```bash
cd backend && go test ./internal/fabquery/ -run TestWrap -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/internal/fabquery/rownum.go backend/internal/fabquery/rownum_test.go
git commit -m "feat: ROWNUM auto-wrap for Oracle pagination"
```

---

## Task 6: `testdb.go` — Test DB Trial Run

**Files:**
- Create: `backend/internal/fabquery/testdb.go`
- Create: `backend/internal/fabquery/testdb_test.go`

- [ ] **Step 1: Write the failing test**

```go
// backend/internal/fabquery/testdb_test.go
package fabquery_test

import (
    "context"
    "encoding/json"
    "net/http"
    "net/http/httptest"
    "testing"
    "time"
    "isop-cpnt/backend/internal/fabquery"
)

func TestTestDBClient_Success(t *testing.T) {
    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        json.NewEncoder(w).Encode(map[string]interface{}{
            "columns": []string{"id"},
            "rows":    []map[string]interface{}{{"id": 1}},
        })
    }))
    defer srv.Close()

    client := fabquery.NewTestDBClient(srv.URL, 5)
    err := client.TryRun(context.Background(), "SELECT 1 FROM dual", nil)
    if err != nil {
        t.Fatalf("expected no error, got: %v", err)
    }
}

func TestTestDBClient_Timeout(t *testing.T) {
    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        time.Sleep(200 * time.Millisecond)
        w.WriteHeader(200)
    }))
    defer srv.Close()

    client := fabquery.NewTestDBClient(srv.URL, 0) // 0s timeout → immediate
    err := client.TryRun(context.Background(), "SELECT 1 FROM dual", nil)
    if err == nil {
        t.Fatal("expected timeout error, got nil")
    }
}

func TestTestDBClient_DBError(t *testing.T) {
    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.WriteHeader(400)
        json.NewEncoder(w).Encode(map[string]string{"detail": "ORA-00942: table not found"})
    }))
    defer srv.Close()

    client := fabquery.NewTestDBClient(srv.URL, 5)
    err := client.TryRun(context.Background(), "SELECT * FROM no_table", nil)
    if err == nil {
        t.Fatal("expected error for DB 400, got nil")
    }
}
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && go test ./internal/fabquery/ -run TestTestDB -v
```

Expected: compilation error

- [ ] **Step 3: Write implementation**

```go
// backend/internal/fabquery/testdb.go
package fabquery

import (
    "bytes"
    "context"
    "encoding/json"
    "fmt"
    "net/http"
    "time"
)

type TestDBClient struct {
    url     string
    timeout time.Duration
}

func NewTestDBClient(url string, timeoutSeconds int) *TestDBClient {
    return &TestDBClient{url: url, timeout: time.Duration(timeoutSeconds) * time.Second}
}

func (c *TestDBClient) TryRun(ctx context.Context, sql string, params map[string]interface{}) error {
    if params == nil {
        params = map[string]interface{}{}
    }
    body, _ := json.Marshal(map[string]interface{}{"sql": sql, "params": params})

    ctx, cancel := context.WithTimeout(ctx, c.timeout)
    defer cancel()

    req, _ := http.NewRequestWithContext(ctx, http.MethodPost, c.url+"/query", bytes.NewReader(body))
    req.Header.Set("Content-Type", "application/json")

    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        if ctx.Err() == context.DeadlineExceeded {
            return fmt.Errorf("query too slow: exceeded %s timeout on test DB", c.timeout)
        }
        return fmt.Errorf("test DB unreachable: %v", err)
    }
    defer resp.Body.Close()

    if resp.StatusCode != http.StatusOK {
        var errBody struct {
            Detail string `json:"detail"`
        }
        json.NewDecoder(resp.Body).Decode(&errBody)
        return fmt.Errorf("test DB rejected query: %s", errBody.Detail)
    }
    return nil
}
```

- [ ] **Step 4: Run tests**

```bash
cd backend && go test ./internal/fabquery/ -run TestTestDB -v
```

Expected: 3 cases PASS

- [ ] **Step 5: Commit**

```bash
git add backend/internal/fabquery/testdb.go backend/internal/fabquery/testdb_test.go
git commit -m "feat: Test DB trial run with configurable timeout"
```

---

## Task 7: `engine.go` — Goroutine Fan-Out

**Files:**
- Create: `backend/internal/fabquery/engine.go`
- Create: `backend/internal/fabquery/engine_test.go`

- [ ] **Step 1: Write the failing test**

```go
// backend/internal/fabquery/engine_test.go
package fabquery_test

import (
    "context"
    "encoding/json"
    "net/http"
    "net/http/httptest"
    "testing"
    "isop-cpnt/backend/internal/fabquery"
)

func makeMockSidecar(t *testing.T, rows []map[string]interface{}) *httptest.Server {
    t.Helper()
    return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        json.NewEncoder(w).Encode(map[string]interface{}{
            "columns": []string{"name"},
            "rows":    rows,
        })
    }))
}

func TestEngine_AllFabsSucceed(t *testing.T) {
    srv1 := makeMockSidecar(t, []map[string]interface{}{{"name": "cpnt_a"}})
    srv2 := makeMockSidecar(t, []map[string]interface{}{{"name": "cpnt_b"}})
    defer srv1.Close()
    defer srv2.Close()

    urls := map[string]string{"F12A": srv1.URL, "F12B": srv2.URL}
    engine := fabquery.NewEngine(urls, 5)
    ch := engine.Execute(context.Background(), "SELECT name FROM cpnt", []string{"F12A", "F12B"}, nil)

    results := collect(ch)
    if len(results) != 2 {
        t.Fatalf("expected 2 results, got %d", len(results))
    }
    for _, r := range results {
        if r.Status != "ok" {
            t.Errorf("fab %s expected ok, got %s: %s", r.Fab, r.Status, r.Error)
        }
    }
}

func TestEngine_PartialFailure(t *testing.T) {
    good := makeMockSidecar(t, []map[string]interface{}{{"name": "ok"}})
    bad := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.WriteHeader(400)
        json.NewEncoder(w).Encode(map[string]string{"detail": "ORA error"})
    }))
    defer good.Close()
    defer bad.Close()

    urls := map[string]string{"F12A": good.URL, "F12B": bad.URL}
    engine := fabquery.NewEngine(urls, 5)
    ch := engine.Execute(context.Background(), "SELECT name FROM cpnt", []string{"F12A", "F12B"}, nil)

    results := collect(ch)
    if len(results) != 2 {
        t.Fatalf("expected 2 results, got %d", len(results))
    }
    statuses := map[string]string{}
    for _, r := range results {
        statuses[r.Fab] = r.Status
    }
    if statuses["F12A"] != "ok" || statuses["F12B"] != "error" {
        t.Errorf("unexpected statuses: %v", statuses)
    }
}

func collect(ch <-chan fabquery.FabResult) []fabquery.FabResult {
    var results []fabquery.FabResult
    for r := range ch {
        results = append(results, r)
    }
    return results
}
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && go test ./internal/fabquery/ -run TestEngine -v
```

Expected: compilation error

- [ ] **Step 3: Write implementation**

```go
// backend/internal/fabquery/engine.go
package fabquery

import (
    "bytes"
    "context"
    "encoding/json"
    "fmt"
    "net/http"
    "sync"
    "time"
)

type FabResult struct {
    Fab     string                   `json:"fab"`
    Columns []string                 `json:"columns,omitempty"`
    Rows    []map[string]interface{} `json:"rows,omitempty"`
    Status  string                   `json:"status"` // "ok" | "error"
    Error   string                   `json:"error,omitempty"`
}

type Engine struct {
    sidecars map[string]string
    timeout  time.Duration
}

func NewEngine(sidecars map[string]string, timeoutSeconds int) *Engine {
    return &Engine{sidecars: sidecars, timeout: time.Duration(timeoutSeconds) * time.Second}
}

func (e *Engine) Execute(ctx context.Context, sql string, fabs []string, params map[string]interface{}) <-chan FabResult {
    if params == nil {
        params = map[string]interface{}{}
    }
    ch := make(chan FabResult, len(fabs))
    var wg sync.WaitGroup
    for _, fab := range fabs {
        wg.Add(1)
        go func(fab string) {
            defer wg.Done()
            ch <- e.queryFab(ctx, fab, sql, params)
        }(fab)
    }
    go func() {
        wg.Wait()
        close(ch)
    }()
    return ch
}

func (e *Engine) queryFab(ctx context.Context, fab, sql string, params map[string]interface{}) FabResult {
    url, ok := e.sidecars[fab]
    if !ok {
        return FabResult{Fab: fab, Status: "error", Error: fmt.Sprintf("unknown fab: %s", fab)}
    }

    ctx, cancel := context.WithTimeout(ctx, e.timeout)
    defer cancel()

    body, _ := json.Marshal(map[string]interface{}{"sql": sql, "params": params})
    req, _ := http.NewRequestWithContext(ctx, http.MethodPost, url+"/query", bytes.NewReader(body))
    req.Header.Set("Content-Type", "application/json")

    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        return FabResult{Fab: fab, Status: "error", Error: err.Error()}
    }
    defer resp.Body.Close()

    var payload struct {
        Columns []string                 `json:"columns"`
        Rows    []map[string]interface{} `json:"rows"`
        Detail  string                   `json:"detail"`
    }
    json.NewDecoder(resp.Body).Decode(&payload)

    if resp.StatusCode != http.StatusOK {
        return FabResult{Fab: fab, Status: "error", Error: payload.Detail}
    }
    return FabResult{Fab: fab, Status: "ok", Columns: payload.Columns, Rows: payload.Rows}
}
```

- [ ] **Step 4: Run tests**

```bash
cd backend && go test ./internal/fabquery/ -run TestEngine -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/internal/fabquery/engine.go backend/internal/fabquery/engine_test.go
git commit -m "feat: fabquery engine — goroutine fan-out per fab with partial failure support"
```

---

## Task 8: `sse.go` — SSE Event Writer

**Files:**
- Create: `backend/internal/fabquery/sse.go`

- [ ] **Step 1: Write implementation (no separate test — tested via handler integration test)**

```go
// backend/internal/fabquery/sse.go
package fabquery

import (
    "encoding/json"
    "fmt"
    "net/http"
)

func WriteSSEEvent(w http.ResponseWriter, event string, data interface{}) {
    payload, err := json.Marshal(data)
    if err != nil {
        return
    }
    fmt.Fprintf(w, "event: %s\ndata: %s\n\n", event, payload)
    if f, ok := w.(http.Flusher); ok {
        f.Flush()
    }
}

func SetSSEHeaders(w http.ResponseWriter) {
    w.Header().Set("Content-Type", "text/event-stream")
    w.Header().Set("Cache-Control", "no-cache")
    w.Header().Set("Connection", "keep-alive")
    w.Header().Set("Access-Control-Allow-Origin", "*")
}
```

- [ ] **Step 2: Commit**

```bash
git add backend/internal/fabquery/sse.go
git commit -m "feat: SSE event writer helper"
```

---

## Task 9: Context SQL Templates Config

**Files:**
- Create: `backend/config/context_sqls.yaml`
- Create: `backend/internal/console/templates.go`
- Create: `backend/internal/console/templates_test.go`

- [ ] **Step 1: Write `config/context_sqls.yaml`**

```yaml
sqls:
  - id: failed-cpnt-recent
    name: 查詢最近失敗的 Cpnt
    description: 依天數查詢最近有執行失敗記錄的 Cpnt 與錯誤訊息
    sql: |
      SELECT c.name, e.error_msg, e.fail_time
      FROM cpnt c JOIN cpnt_execution_log e ON c.id = e.cpnt_id
      WHERE e.status = 'FAILED' AND e.fail_time > SYSDATE - :days
      ORDER BY e.fail_time DESC
    params:
      - name: days
        label: 天數
        type: integer
        default: 7

  - id: active-cpnts
    name: 查詢啟用中的 Cpnt
    description: 列出所有狀態為 ACTIVE 的 Cpnt 設定
    sql: |
      SELECT c.name, c.api_url, c.method, c.created_at
      FROM cpnt c
      WHERE c.status = 'ACTIVE'
      ORDER BY c.name

  - id: sop-cpnt-mapping
    name: SOP 與 Cpnt 對應關係
    description: 查詢特定 SOP 呼叫了哪些 Cpnt
    sql: |
      SELECT s.name AS sop_name, c.name AS cpnt_name, sc.step_order
      FROM sop s
      JOIN sop_cpnt sc ON s.id = sc.sop_id
      JOIN cpnt c ON sc.cpnt_id = c.id
      WHERE s.name LIKE :sop_pattern
      ORDER BY s.name, sc.step_order
    params:
      - name: sop_pattern
        label: SOP 名稱（支援 % 萬用字元）
        type: string
        default: "%"
```

- [ ] **Step 2: Write failing test for templates loader**

```go
// backend/internal/console/templates_test.go
package console_test

import (
    "os"
    "testing"
    "isop-cpnt/backend/internal/console"
)

func TestLoadTemplates_Success(t *testing.T) {
    yaml := `
sqls:
  - id: test-sql
    name: Test
    description: A test
    sql: SELECT 1 FROM dual
`
    f, _ := os.CreateTemp("", "*.yaml")
    f.WriteString(yaml)
    f.Close()
    defer os.Remove(f.Name())

    templates, err := console.LoadTemplates(f.Name())
    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }
    if len(templates) != 1 || templates[0].ID != "test-sql" {
        t.Errorf("unexpected templates: %+v", templates)
    }
}

func TestLoadTemplates_MissingID(t *testing.T) {
    yaml := `
sqls:
  - name: Missing ID
    sql: SELECT 1 FROM dual
`
    f, _ := os.CreateTemp("", "*.yaml")
    f.WriteString(yaml)
    f.Close()
    defer os.Remove(f.Name())

    _, err := console.LoadTemplates(f.Name())
    if err == nil {
        t.Fatal("expected error for missing id, got nil")
    }
}
```

- [ ] **Step 3: Run to verify failure**

```bash
cd backend && go test ./internal/console/ -run TestLoadTemplates -v
```

Expected: compilation error

- [ ] **Step 4: Write `internal/console/templates.go`**

```go
// backend/internal/console/templates.go
package console

import (
    "fmt"
    "os"

    "gopkg.in/yaml.v3"
)

type SqlParam struct {
    Name    string      `yaml:"name"    json:"name"`
    Label   string      `yaml:"label"   json:"label"`
    Type    string      `yaml:"type"    json:"type"`
    Default interface{} `yaml:"default" json:"default"`
}

type SqlTemplate struct {
    ID          string     `yaml:"id"          json:"id"`
    Name        string     `yaml:"name"        json:"name"`
    Description string     `yaml:"description" json:"description"`
    SQL         string     `yaml:"sql"         json:"sql"`
    Params      []SqlParam `yaml:"params"      json:"params"`
}

func LoadTemplates(path string) ([]SqlTemplate, error) {
    data, err := os.ReadFile(path)
    if err != nil {
        return nil, fmt.Errorf("reading %s: %w", path, err)
    }
    var cfg struct {
        Sqls []SqlTemplate `yaml:"sqls"`
    }
    if err := yaml.Unmarshal(data, &cfg); err != nil {
        return nil, fmt.Errorf("parsing %s: %w", path, err)
    }
    for i, t := range cfg.Sqls {
        if t.ID == "" {
            return nil, fmt.Errorf("template[%d] missing required field: id", i)
        }
        if t.SQL == "" {
            return nil, fmt.Errorf("template %q missing required field: sql", t.ID)
        }
    }
    return cfg.Sqls, nil
}
```

- [ ] **Step 5: Run tests**

```bash
cd backend && go test ./internal/console/ -run TestLoadTemplates -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/config/context_sqls.yaml backend/internal/console/templates.go backend/internal/console/templates_test.go
git commit -m "feat: context SQL templates — YAML config + loader with validation"
```

---

## Task 10: `console/handler.go` — POST /api/fabs/query

**Files:**
- Create: `backend/internal/console/handler.go`
- Create: `backend/internal/console/handler_test.go`

- [ ] **Step 1: Write failing tests for POST endpoint**

```go
// backend/internal/console/handler_test.go
package console_test

import (
    "bytes"
    "context"
    "encoding/json"
    "net/http"
    "net/http/httptest"
    "testing"
    "isop-cpnt/backend/internal/console"
    "isop-cpnt/backend/internal/fabquery"
)

// stubTestDB always succeeds
type stubTestDB struct{ err error }
func (s *stubTestDB) TryRun(_ context.Context, _ string, _ map[string]interface{}) error {
    return s.err
}

func newTestHandler(testDBErr error) *console.Handler {
    engine := fabquery.NewEngine(map[string]string{"F12A": "http://unused"}, 5)
    testDB := &stubTestDB{err: testDBErr}
    return console.NewHandler(engine, testDB, nil)
}

func postExecute(t *testing.T, h *console.Handler, body interface{}) *httptest.ResponseRecorder {
    t.Helper()
    b, _ := json.Marshal(body)
    req := httptest.NewRequest(http.MethodPost, "/api/fabs/query", bytes.NewReader(b))
    req.Header.Set("Content-Type", "application/json")
    w := httptest.NewRecorder()
    h.Execute(w, req)
    return w
}

func TestExecute_NonSelectRejected(t *testing.T) {
    h := newTestHandler(nil)
    w := postExecute(t, h, map[string]interface{}{
        "sql": "DELETE FROM cpnt", "fabs": []string{"F12A"}, "rowLimit": 100,
    })
    if w.Code != 400 {
        t.Errorf("expected 400, got %d", w.Code)
    }
}

func TestExecute_NoFabsRejected(t *testing.T) {
    h := newTestHandler(nil)
    w := postExecute(t, h, map[string]interface{}{
        "sql": "SELECT 1 FROM dual", "fabs": []string{}, "rowLimit": 100,
    })
    if w.Code != 400 {
        t.Errorf("expected 400, got %d", w.Code)
    }
}

func TestExecute_RowLimitExceededRejected(t *testing.T) {
    h := newTestHandler(nil)
    w := postExecute(t, h, map[string]interface{}{
        "sql": "SELECT 1 FROM dual", "fabs": []string{"F12A"}, "rowLimit": 500,
    })
    if w.Code != 400 {
        t.Errorf("expected 400, got %d", w.Code)
    }
}

func TestExecute_TestDBFailRejected(t *testing.T) {
    h := newTestHandler(fmt.Errorf("query too slow"))
    w := postExecute(t, h, map[string]interface{}{
        "sql": "SELECT 1 FROM dual", "fabs": []string{"F12A"}, "rowLimit": 100,
    })
    if w.Code != 400 {
        t.Errorf("expected 400, got %d", w.Code)
    }
}

func TestExecute_ValidRequestReturnsQueryId(t *testing.T) {
    h := newTestHandler(nil)
    w := postExecute(t, h, map[string]interface{}{
        "sql": "SELECT 1 FROM dual", "fabs": []string{"F12A"}, "rowLimit": 100,
    })
    if w.Code != 200 {
        t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
    }
    var resp map[string]string
    json.NewDecoder(w.Body).Decode(&resp)
    if resp["queryId"] == "" {
        t.Error("expected queryId in response")
    }
}
```

Add `"fmt"` to imports.

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && go test ./internal/console/ -run TestExecute -v
```

Expected: compilation error

- [ ] **Step 3: Write `internal/console/handler.go` (Execute part)**

```go
// backend/internal/console/handler.go
package console

import (
    "context"
    "encoding/json"
    "net/http"
    "sync"
    "time"

    "github.com/go-chi/chi/v5"
    "github.com/google/uuid"
    "isop-cpnt/backend/internal/fabquery"
)

type TestDB interface {
    TryRun(ctx context.Context, sql string, params map[string]interface{}) error
}

type storedQuery struct {
    wrappedSQL  string
    fabs        []string
    namedParams map[string]interface{}
    expiresAt   time.Time
}

type Handler struct {
    engine    *fabquery.Engine
    testDB    TestDB
    templates []SqlTemplate
    store     sync.Map // queryID -> storedQuery
}

func NewHandler(engine *fabquery.Engine, testDB TestDB, templates []SqlTemplate) *Handler {
    return &Handler{engine: engine, testDB: testDB, templates: templates}
}

type executeRequest struct {
    SQL         string                 `json:"sql"`
    Fabs        []string               `json:"fabs"`
    RowLimit    int                    `json:"rowLimit"`
    NamedParams map[string]interface{} `json:"namedParams"`
}

func writeJSON(w http.ResponseWriter, code int, v interface{}) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(code)
    json.NewEncoder(w).Encode(v)
}

func (h *Handler) Execute(w http.ResponseWriter, r *http.Request) {
    var req executeRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        writeJSON(w, 400, map[string]string{"error": "invalid request body"})
        return
    }
    if err := fabquery.ValidateSelectOnly(req.SQL); err != nil {
        writeJSON(w, 400, map[string]string{"error": err.Error()})
        return
    }
    if len(req.Fabs) == 0 {
        writeJSON(w, 400, map[string]string{"error": "at least one fab required"})
        return
    }
    if req.RowLimit <= 0 {
        req.RowLimit = 100
    }
    if req.RowLimit > 300 {
        writeJSON(w, 400, map[string]string{"error": "rowLimit max is 300"})
        return
    }

    wrappedSQL := fabquery.WrapWithRownum(req.SQL, req.RowLimit)

    if err := h.testDB.TryRun(r.Context(), wrappedSQL, req.NamedParams); err != nil {
        writeJSON(w, 400, map[string]string{"error": err.Error()})
        return
    }

    queryID := uuid.New().String()
    h.store.Store(queryID, storedQuery{
        wrappedSQL:  wrappedSQL,
        fabs:        req.Fabs,
        namedParams: req.NamedParams,
        expiresAt:   time.Now().Add(5 * time.Minute),
    })

    writeJSON(w, 200, map[string]string{"queryId": queryID})
}

func (h *Handler) Templates(w http.ResponseWriter, r *http.Request) {
    writeJSON(w, 200, h.templates)
}
```

- [ ] **Step 4: Run tests**

```bash
cd backend && go test ./internal/console/ -run TestExecute -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/internal/console/handler.go backend/internal/console/handler_test.go
git commit -m "feat: POST /api/fabs/query handler — validate, wrap ROWNUM, trial run, issue queryId"
```

---

## Task 11: `console/handler.go` — GET /api/fabs/stream/{id} (SSE)

**Files:**
- Modify: `backend/internal/console/handler.go` (add Stream method)
- Modify: `backend/internal/console/handler_test.go` (add SSE test)

- [ ] **Step 1: Add SSE integration test**

Append to `handler_test.go`:

```go
func TestStream_SendsSSEEvents(t *testing.T) {
    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        json.NewEncoder(w).Encode(map[string]interface{}{
            "columns": []string{"name"},
            "rows":    []map[string]interface{}{{"name": "cpnt_a"}},
        })
    }))
    defer srv.Close()

    engine := fabquery.NewEngine(map[string]string{"F12A": srv.URL}, 5)
    testDB := &stubTestDB{err: nil}
    h := console.NewHandler(engine, testDB, nil)

    // First: create query
    w := postExecute(t, h, map[string]interface{}{
        "sql": "SELECT name FROM cpnt", "fabs": []string{"F12A"}, "rowLimit": 10,
    })
    var execResp map[string]string
    json.NewDecoder(w.Body).Decode(&execResp)
    queryID := execResp["queryId"]

    // Then: stream it
    req := httptest.NewRequest(http.MethodGet, "/api/fabs/stream/"+queryID, nil)
    req = req.WithContext(chi.NewRouteContext())
    // inject chi param
    rctx := chi.RouteContext(req.Context())
    rctx.URLParams.Add("id", queryID)

    streamW := httptest.NewRecorder()
    h.Stream(streamW, req)

    body := streamW.Body.String()
    if !strings.Contains(body, "fab_result") {
        t.Errorf("expected fab_result event, got:\n%s", body)
    }
    if !strings.Contains(body, "done") {
        t.Errorf("expected done event, got:\n%s", body)
    }
}
```

Add `"strings"` and `"github.com/go-chi/chi/v5"` to imports.

- [ ] **Step 2: Add Stream method to `handler.go`**

```go
func (h *Handler) Stream(w http.ResponseWriter, r *http.Request) {
    queryID := chi.URLParam(r, "id")

    val, ok := h.store.Load(queryID)
    if !ok {
        writeJSON(w, 404, map[string]string{"error": "query not found or expired"})
        return
    }
    q := val.(storedQuery)
    if time.Now().After(q.expiresAt) {
        h.store.Delete(queryID)
        writeJSON(w, 404, map[string]string{"error": "query expired, please re-execute"})
        return
    }

    fabquery.SetSSEHeaders(w)

    resultCh := h.engine.Execute(r.Context(), q.wrappedSQL, q.fabs, q.namedParams)
    for result := range resultCh {
        if result.Status == "error" {
            fabquery.WriteSSEEvent(w, "fab_error", map[string]string{
                "fab":     result.Fab,
                "message": result.Error,
            })
        } else {
            fabquery.WriteSSEEvent(w, "fab_result", result)
        }
    }
    fabquery.WriteSSEEvent(w, "done", map[string]string{"status": "complete"})
}
```

- [ ] **Step 3: Run all console tests**

```bash
cd backend && go test ./internal/console/ -v
```

Expected: all PASS

- [ ] **Step 4: Build to verify everything compiles**

```bash
cd backend && go build ./...
```

Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add backend/internal/console/handler.go backend/internal/console/handler_test.go
git commit -m "feat: GET /api/fabs/stream/{id} SSE endpoint — fan-out results per fab"
```

---

## Task 12: Angular App Scaffold

**Files:**
- Create: `frontend/` (Angular CLI init)

- [ ] **Step 1: Scaffold Angular app**

```bash
cd frontend
ng new . --standalone --routing --style=css --skip-git --skip-tests
```

- [ ] **Step 2: Install Monaco Editor**

```bash
npm install @monaco-editor/angular monaco-editor
```

- [ ] **Step 3: Configure Monaco assets in `angular.json`**

In `angular.json`, inside `projects.<name>.architect.build.options`, add to `assets`:

```json
{
  "glob": "**/*",
  "input": "node_modules/monaco-editor/min/vs",
  "output": "/assets/vs"
}
```

- [ ] **Step 4: Create directory structure**

```bash
mkdir -p src/app/models src/app/services
mkdir -p src/app/shared/fab-selector src/app/shared/results
mkdir -p src/app/sql-console/context-sql src/app/sql-console/sql-editor
```

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold Angular 21 standalone app with Monaco Editor"
```

---

## Task 13: TypeScript Models + `detectDiff`

**Files:**
- Create: `frontend/src/app/models/fab-query.models.ts`
- Create: `frontend/src/app/models/fab-query.models.spec.ts`

- [ ] **Step 1: Write failing test**

```typescript
// frontend/src/app/models/fab-query.models.spec.ts
import { detectDiff, FabResult } from './fab-query.models';

describe('detectDiff', () => {
  const makeResult = (fab: string, rows: Record<string, unknown>[]): FabResult => ({
    fab,
    columns: Object.keys(rows[0] ?? {}),
    rows,
    status: 'ok',
  });

  it('returns empty set when fewer than 2 ok fabs', () => {
    const result = detectDiff([makeResult('F12A', [{ name: 'x' }])]);
    expect(result.size).toBe(0);
  });

  it('returns empty set when all values agree', () => {
    const results = [
      makeResult('F12A', [{ name: 'cpnt_a' }]),
      makeResult('F12B', [{ name: 'cpnt_a' }]),
    ];
    expect(detectDiff(results).size).toBe(0);
  });

  it('returns differing columns when values disagree', () => {
    const results = [
      makeResult('F12A', [{ name: 'cpnt_a', status: 'ACTIVE' }]),
      makeResult('F12B', [{ name: 'cpnt_b', status: 'ACTIVE' }]),
    ];
    const diff = detectDiff(results);
    expect(diff.has('name')).toBeTrue();
    expect(diff.has('status')).toBeFalse();
  });

  it('ignores error fabs in diff calculation', () => {
    const results: FabResult[] = [
      makeResult('F12A', [{ name: 'cpnt_a' }]),
      { fab: 'F12B', columns: [], rows: [], status: 'error', error: 'timeout' },
    ];
    expect(detectDiff(results).size).toBe(0); // only 1 ok fab
  });
});
```

- [ ] **Step 2: Run to verify failure**

```bash
cd frontend && ng test --include='**/fab-query.models.spec.ts' --watch=false
```

Expected: compilation error

- [ ] **Step 3: Write models file**

```typescript
// frontend/src/app/models/fab-query.models.ts
export interface SqlParam {
  name: string;
  label: string;
  type: 'string' | 'integer' | 'date';
  default?: string | number;
}

export interface SqlTemplate {
  id: string;
  name: string;
  description: string;
  sql: string;
  params?: SqlParam[];
}

export interface FabResult {
  fab: string;
  columns: string[];
  rows: Record<string, unknown>[];
  status: 'ok' | 'error';
  error?: string;
}

export type ViewMode = 'flat' | 'diff' | 'pivot';

export function detectDiff(fabResults: FabResult[]): Set<string> {
  const ok = fabResults.filter(r => r.status === 'ok');
  if (ok.length < 2) return new Set();

  const columns = ok[0].columns;
  const diffCols = new Set<string>();

  for (const col of columns) {
    const values = new Set(ok.flatMap(r => r.rows.map(row => String(row[col] ?? ''))));
    if (values.size > 1) diffCols.add(col);
  }
  return diffCols;
}
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && ng test --include='**/fab-query.models.spec.ts' --watch=false
```

Expected: 4 specs PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/models/
git commit -m "feat: TypeScript models + detectDiff algorithm"
```

---

## Task 14: `FabQueryService` — SSE Client

**Files:**
- Create: `frontend/src/app/services/fab-query.service.ts`
- Create: `frontend/src/app/services/fab-query.service.spec.ts`

- [ ] **Step 1: Write failing test**

```typescript
// frontend/src/app/services/fab-query.service.spec.ts
import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { FabQueryService } from './fab-query.service';

describe('FabQueryService', () => {
  let service: FabQueryService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [FabQueryService],
    });
    service = TestBed.inject(FabQueryService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('execute() POSTs to /api/fabs/query and returns queryId', (done) => {
    service.execute('SELECT 1 FROM dual', ['F12A'], 100, {}).subscribe(id => {
      expect(id).toBe('abc-123');
      done();
    });

    const req = httpMock.expectOne('/api/fabs/query');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({
      sql: 'SELECT 1 FROM dual',
      fabs: ['F12A'],
      rowLimit: 100,
      namedParams: {},
    });
    req.flush({ queryId: 'abc-123' });
  });
});
```

- [ ] **Step 2: Run to verify failure**

```bash
cd frontend && ng test --include='**/fab-query.service.spec.ts' --watch=false
```

- [ ] **Step 3: Write service**

```typescript
// frontend/src/app/services/fab-query.service.ts
import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, map } from 'rxjs';
import { FabResult } from '../models/fab-query.models';

export type SseEvent =
  | (FabResult & { type?: never })
  | { type: 'done' };

@Injectable({ providedIn: 'root' })
export class FabQueryService {
  private http = inject(HttpClient);

  execute(
    sql: string,
    fabs: string[],
    rowLimit: number,
    namedParams: Record<string, unknown>,
  ): Observable<string> {
    return this.http
      .post<{ queryId: string }>('/api/fabs/query', { sql, fabs, rowLimit, namedParams })
      .pipe(map(r => r.queryId));
  }

  stream(queryId: string): Observable<SseEvent> {
    return new Observable(subscriber => {
      const es = new EventSource(`/api/fabs/stream/${queryId}`);

      es.addEventListener('fab_result', (e: MessageEvent) => {
        subscriber.next(JSON.parse(e.data) as FabResult);
      });

      es.addEventListener('fab_error', (e: MessageEvent) => {
        const err = JSON.parse(e.data) as { fab: string; message: string };
        subscriber.next({ fab: err.fab, columns: [], rows: [], status: 'error', error: err.message });
      });

      es.addEventListener('done', () => {
        subscriber.next({ type: 'done' });
        subscriber.complete();
        es.close();
      });

      es.onerror = () => {
        subscriber.error(new Error('SSE connection lost'));
        es.close();
      };

      return () => es.close();
    });
  }
}
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && ng test --include='**/fab-query.service.spec.ts' --watch=false
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/services/
git commit -m "feat: FabQueryService — SSE streaming client with Observable wrapper"
```

---

## Task 15: `FabSelectorComponent` (shared)

**Files:**
- Create: `frontend/src/app/shared/fab-selector/fab-selector.component.ts`
- Create: `frontend/src/app/shared/fab-selector/fab-selector.component.html`
- Create: `frontend/src/app/shared/fab-selector/fab-selector.component.spec.ts`

- [ ] **Step 1: Write failing test**

```typescript
// frontend/src/app/shared/fab-selector/fab-selector.component.spec.ts
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FabSelectorComponent } from './fab-selector.component';

describe('FabSelectorComponent', () => {
  let fixture: ComponentFixture<FabSelectorComponent>;
  let component: FabSelectorComponent;

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [FabSelectorComponent] });
    fixture = TestBed.createComponent(FabSelectorComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('starts with no fabs selected', () => {
    expect(component.selected()).toEqual([]);
  });

  it('toggleAll selects all 14 fabs', () => {
    component.toggleAll();
    expect(component.selected().length).toBe(14);
  });

  it('toggleAll when all selected deselects all', () => {
    component.toggleAll();
    component.toggleAll();
    expect(component.selected().length).toBe(0);
  });

  it('toggle individual fab adds/removes it', () => {
    component.toggle('F12A');
    expect(component.selected()).toContain('F12A');
    component.toggle('F12A');
    expect(component.selected()).not.toContain('F12A');
  });
});
```

- [ ] **Step 2: Write component**

```typescript
// frontend/src/app/shared/fab-selector/fab-selector.component.ts
import { ChangeDetectionStrategy, Component, model } from '@angular/core';
import { CommonModule } from '@angular/common';

const ALL_FABS = [
  'F12A', 'F12B', 'F14A', 'F14B', 'F15A', 'F15B',
  'F16', 'F18A', 'F18B', 'F21', 'F22', 'F23', 'APOD', 'SOIC',
];

@Component({
  selector: 'app-fab-selector',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './fab-selector.component.html',
})
export class FabSelectorComponent {
  readonly fabs = ALL_FABS;
  selected = model<string[]>([]);

  isSelected(fab: string): boolean {
    return this.selected().includes(fab);
  }

  toggle(fab: string): void {
    const cur = this.selected();
    this.selected.set(cur.includes(fab) ? cur.filter(f => f !== fab) : [...cur, fab]);
  }

  toggleAll(): void {
    this.selected.set(this.selected().length === this.fabs.length ? [] : [...this.fabs]);
  }

  get allSelected(): boolean {
    return this.selected().length === this.fabs.length;
  }
}
```

```html
<!-- frontend/src/app/shared/fab-selector/fab-selector.component.html -->
<div class="fab-selector">
  <button type="button" (click)="toggleAll()">
    {{ allSelected ? '全不選' : '全選' }}
  </button>
  <div class="fab-chips">
    @for (fab of fabs; track fab) {
      <label class="fab-chip" [class.selected]="isSelected(fab)">
        <input type="checkbox" [checked]="isSelected(fab)" (change)="toggle(fab)" />
        {{ fab }}
      </label>
    }
  </div>
</div>
```

- [ ] **Step 3: Run tests**

```bash
cd frontend && ng test --include='**/fab-selector.component.spec.ts' --watch=false
```

Expected: 4 specs PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/shared/fab-selector/
git commit -m "feat: FabSelectorComponent — multi-select dropdown for 14 fabs"
```

---

## Task 16: `FlatTableComponent` (shared)

**Files:**
- Create: `frontend/src/app/shared/results/flat-table.component.ts`
- Create: `frontend/src/app/shared/results/flat-table.component.html`

- [ ] **Step 1: Write component**

```typescript
// frontend/src/app/shared/results/flat-table.component.ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FabResult } from '../../models/fab-query.models';

@Component({
  selector: 'app-flat-table',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './flat-table.component.html',
})
export class FlatTableComponent {
  results = input<FabResult[]>([]);
  diffColumns = input<Set<string>>(new Set());

  columns = computed(() => {
    const ok = this.results().find(r => r.status === 'ok');
    return ok ? ok.columns : [];
  });

  rows = computed(() =>
    this.results()
      .filter(r => r.status === 'ok')
      .flatMap(r => r.rows.map(row => ({ fab: r.fab, ...row })))
  );

  isDiff(col: string): boolean {
    return this.diffColumns().has(col);
  }
}
```

```html
<!-- frontend/src/app/shared/results/flat-table.component.html -->
<div class="flat-table-container">
  @if (rows().length === 0) {
    <p class="empty-state">查無資料</p>
  } @else {
    <table class="flat-table">
      <thead>
        <tr>
          <th class="fab-col">fab</th>
          @for (col of columns(); track col) {
            <th [class.diff-col]="isDiff(col)">{{ col }}</th>
          }
        </tr>
      </thead>
      <tbody>
        @for (row of rows(); track $index) {
          <tr>
            <td class="fab-col">{{ row['fab'] }}</td>
            @for (col of columns(); track col) {
              <td [class.diff-cell]="isDiff(col)">{{ row[col] }}</td>
            }
          </tr>
        }
      </tbody>
    </table>
  }
</div>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/shared/results/flat-table.component.ts frontend/src/app/shared/results/flat-table.component.html
git commit -m "feat: FlatTableComponent — merged fab results table with diff highlight support"
```

---

## Task 17: `DiffPanelComponent` + `PivotViewComponent` (shared)

**Files:**
- Create: `frontend/src/app/shared/results/diff-panel.component.ts`
- Create: `frontend/src/app/shared/results/diff-panel.component.html`
- Create: `frontend/src/app/shared/results/pivot-view.component.ts`
- Create: `frontend/src/app/shared/results/pivot-view.component.html`

- [ ] **Step 1: Write `DiffPanelComponent`**

```typescript
// frontend/src/app/shared/results/diff-panel.component.ts
import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-diff-panel',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './diff-panel.component.html',
})
export class DiffPanelComponent {
  diffColumns = input<Set<string>>(new Set());

  get diffList(): string[] {
    return Array.from(this.diffColumns());
  }
}
```

```html
<!-- frontend/src/app/shared/results/diff-panel.component.html -->
<div class="diff-panel">
  @if (diffList.length === 0) {
    <p class="no-diff">所有選定廠區資料一致</p>
  } @else {
    <p class="diff-summary">差異欄位（{{ diffList.length }}）：</p>
    <ul class="diff-columns">
      @for (col of diffList; track col) {
        <li>{{ col }}</li>
      }
    </ul>
  }
</div>
```

- [ ] **Step 2: Write `PivotViewComponent`**

```typescript
// frontend/src/app/shared/results/pivot-view.component.ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FabResult } from '../../models/fab-query.models';

@Component({
  selector: 'app-pivot-view',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './pivot-view.component.html',
})
export class PivotViewComponent {
  results = input<FabResult[]>([]);

  okResults = computed(() => this.results().filter(r => r.status === 'ok'));
  fabs = computed(() => this.okResults().map(r => r.fab));
  columns = computed(() => this.okResults()[0]?.columns ?? []);

  // For pivot: each column → map of fab→first-row-value
  pivotRows = computed(() =>
    this.columns().map(col => ({
      field: col,
      values: Object.fromEntries(
        this.okResults().map(r => [r.fab, r.rows[0]?.[col] ?? ''])
      ),
    }))
  );
}
```

```html
<!-- frontend/src/app/shared/results/pivot-view.component.html -->
<div class="pivot-container">
  @if (pivotRows().length === 0) {
    <p class="empty-state">查無資料</p>
  } @else {
    <table class="pivot-table">
      <thead>
        <tr>
          <th>欄位</th>
          @for (fab of fabs(); track fab) {
            <th>{{ fab }}</th>
          }
        </tr>
      </thead>
      <tbody>
        @for (row of pivotRows(); track row.field) {
          <tr>
            <td class="field-col">{{ row.field }}</td>
            @for (fab of fabs(); track fab) {
              <td>{{ row.values[fab] }}</td>
            }
          </tr>
        }
      </tbody>
    </table>
  }
</div>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/shared/results/diff-panel.component.* frontend/src/app/shared/results/pivot-view.component.*
git commit -m "feat: DiffPanelComponent + PivotViewComponent (shared results)"
```

---

## Task 18: `ResultsComponent` + `FabStatusChipComponent` (shared)

**Files:**
- Create: `frontend/src/app/shared/results/fab-status-chip.component.ts`
- Create: `frontend/src/app/shared/results/results.component.ts`
- Create: `frontend/src/app/shared/results/results.component.html`

- [ ] **Step 1: Write `FabStatusChipComponent`**

```typescript
// frontend/src/app/shared/results/fab-status-chip.component.ts
import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { CommonModule } from '@angular/common';

export type ChipState = 'loading' | 'done' | 'error';

@Component({
  selector: 'app-fab-status-chip',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="chip" [class]="'chip--' + state()">
      {{ fab() }} <span class="chip__icon">{{ icon() }}</span>
    </span>
  `,
})
export class FabStatusChipComponent {
  fab = input.required<string>();
  state = input<ChipState>('loading');

  get icon(): () => string {
    return () => ({ loading: '…', done: '✓', error: '✗' }[this.state()] ?? '');
  }
}
```

- [ ] **Step 2: Write `ResultsComponent`**

```typescript
// frontend/src/app/shared/results/results.component.ts
import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FabResult, ViewMode, detectDiff } from '../../models/fab-query.models';
import { FlatTableComponent } from './flat-table.component';
import { DiffPanelComponent } from './diff-panel.component';
import { PivotViewComponent } from './pivot-view.component';
import { FabStatusChipComponent } from './fab-status-chip.component';

@Component({
  selector: 'app-results',
  standalone: true,
  imports: [CommonModule, FlatTableComponent, DiffPanelComponent, PivotViewComponent, FabStatusChipComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './results.component.html',
})
export class ResultsComponent {
  results = input<FabResult[]>([]);
  loadingFabs = input<string[]>([]);

  viewMode = signal<ViewMode>('flat');
  showDiff = computed(() => this.viewMode() === 'diff');
  diffColumns = computed(() => detectDiff(this.results()));

  setView(mode: ViewMode): void {
    this.viewMode.set(mode);
  }

  fabState(fab: string): 'loading' | 'done' | 'error' {
    if (this.loadingFabs().includes(fab)) return 'loading';
    const r = this.results().find(r => r.fab === fab);
    return r?.status === 'error' ? 'error' : 'done';
  }

  get allFabs(): string[] {
    const done = this.results().map(r => r.fab);
    return [...new Set([...this.loadingFabs(), ...done])];
  }

  get errors(): FabResult[] {
    return this.results().filter(r => r.status === 'error');
  }
}
```

```html
<!-- frontend/src/app/shared/results/results.component.html -->
<div class="results">
  <!-- Fab status chips -->
  <div class="fab-status-bar">
    @for (fab of allFabs; track fab) {
      <app-fab-status-chip [fab]="fab" [state]="fabState(fab)" />
    }
  </div>

  <!-- Error banner -->
  @if (errors.length > 0) {
    <div class="error-banner">
      {{ errors.length }} 個廠區查詢失敗：
      @for (e of errors; track e.fab) {
        <span>{{ e.fab }}（{{ e.error }}）</span>
      }
    </div>
  }

  <!-- View mode controls -->
  <div class="view-controls">
    <button (click)="setView('flat')" [class.active]="viewMode() === 'flat'">Flat</button>
    <button (click)="setView('diff')" [class.active]="viewMode() === 'diff'">Diff</button>
    <button (click)="setView('pivot')" [class.active]="viewMode() === 'pivot'">Pivot</button>
  </div>

  <!-- Diff panel (shown when diff mode active) -->
  @if (viewMode() === 'diff') {
    <app-diff-panel [diffColumns]="diffColumns()" />
  }

  <!-- Main content -->
  @switch (viewMode()) {
    @case ('flat') {
      <app-flat-table [results]="results()" [diffColumns]="new Set()" />
    }
    @case ('diff') {
      <app-flat-table [results]="results()" [diffColumns]="diffColumns()" />
    }
    @case ('pivot') {
      <app-pivot-view [results]="results()" />
    }
  }
</div>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/shared/results/
git commit -m "feat: ResultsComponent + FabStatusChip — view mode switching (flat/diff/pivot)"
```

---

## Task 19: `SqlEditorComponent` (Monaco)

**Files:**
- Create: `frontend/src/app/sql-console/sql-editor/sql-editor.component.ts`
- Create: `frontend/src/app/sql-console/sql-editor/sql-editor.component.html`

- [ ] **Step 1: Write component**

```typescript
// frontend/src/app/sql-console/sql-editor/sql-editor.component.ts
import { ChangeDetectionStrategy, Component, model, OnInit } from '@angular/core';
import { MonacoEditorModule } from '@monaco-editor/angular';

@Component({
  selector: 'app-sql-editor',
  standalone: true,
  imports: [MonacoEditorModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './sql-editor.component.html',
})
export class SqlEditorComponent {
  sql = model<string>('');

  editorOptions = {
    theme: 'vs-dark',
    language: 'sql',
    minimap: { enabled: false },
    fontSize: 13,
    fontFamily: "'IBM Plex Mono', monospace",
    lineNumbers: 'on' as const,
    scrollBeyondLastLine: false,
    automaticLayout: true,
  };

  onEditorInit(editor: unknown): void {
    // Monaco editor initialized — no additional setup needed
  }
}
```

```html
<!-- frontend/src/app/sql-console/sql-editor/sql-editor.component.html -->
<ngx-monaco-editor
  class="sql-editor"
  [options]="editorOptions"
  [(ngModel)]="sql"
  (onInit)="onEditorInit($event)"
/>
```

Add `FormsModule` to imports for `ngModel` binding.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/sql-console/sql-editor/
git commit -m "feat: SqlEditorComponent — Monaco Editor wrapper for Oracle SQL input"
```

---

## Task 20: `NamedParamDirective`

**Files:**
- Create: `frontend/src/app/sql-console/sql-editor/named-param.directive.ts`
- Create: `frontend/src/app/sql-console/sql-editor/named-param.directive.spec.ts`

- [ ] **Step 1: Write failing test**

```typescript
// frontend/src/app/sql-console/sql-editor/named-param.directive.spec.ts
import { extractNamedParams } from './named-param.directive';

describe('extractNamedParams', () => {
  it('extracts params from SQL', () => {
    const params = extractNamedParams('SELECT * FROM t WHERE d > SYSDATE - :days AND name = :name');
    expect(params).toEqual(['days', 'name']);
  });

  it('deduplicates repeated params', () => {
    const params = extractNamedParams('SELECT :x, :x FROM dual');
    expect(params).toEqual(['x']);
  });

  it('returns empty for SQL without params', () => {
    expect(extractNamedParams('SELECT 1 FROM dual')).toEqual([]);
  });
});
```

- [ ] **Step 2: Run to verify failure**

```bash
cd frontend && ng test --include='**/named-param.directive.spec.ts' --watch=false
```

- [ ] **Step 3: Write directive**

```typescript
// frontend/src/app/sql-console/sql-editor/named-param.directive.ts
import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

export function extractNamedParams(sql: string): string[] {
  const matches = sql.match(/:([a-zA-Z_][a-zA-Z0-9_]*)/g) ?? [];
  return [...new Set(matches.map(m => m.slice(1)))];
}

@Component({
  selector: 'app-named-param-inputs',
  standalone: true,
  imports: [CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (params().length > 0) {
      <div class="named-params">
        @for (param of params(); track param) {
          <label class="param-field">
            <span>{{ param }}</span>
            <input
              type="text"
              [value]="values()[param] ?? ''"
              (input)="onInput(param, $event)"
              [placeholder]="param"
            />
          </label>
        }
      </div>
    }
  `,
})
export class NamedParamInputsComponent {
  sql = input<string>('');
  params = computed(() => extractNamedParams(this.sql()));
  valuesChange = output<Record<string, unknown>>();

  values = computed<Record<string, unknown>>(() => ({}));
  private _values: Record<string, unknown> = {};

  onInput(param: string, event: Event): void {
    this._values = { ...this._values, [param]: (event.target as HTMLInputElement).value };
    this.valuesChange.emit(this._values);
  }
}
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && ng test --include='**/named-param.directive.spec.ts' --watch=false
```

Expected: 3 specs PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/sql-console/sql-editor/named-param.directive.ts frontend/src/app/sql-console/sql-editor/named-param.directive.spec.ts
git commit -m "feat: NamedParamInputsComponent — auto-render :param inputs from SQL"
```

---

## Task 21: `ContextSqlComponent` + Service

**Files:**
- Create: `frontend/src/app/sql-console/context-sql/context-sql.service.ts`
- Create: `frontend/src/app/sql-console/context-sql/context-sql.component.ts`
- Create: `frontend/src/app/sql-console/context-sql/context-sql.component.html`

- [ ] **Step 1: Write service**

```typescript
// frontend/src/app/sql-console/context-sql/context-sql.service.ts
import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { SqlTemplate } from '../../models/fab-query.models';

@Injectable({ providedIn: 'root' })
export class ContextSqlService {
  private http = inject(HttpClient);
  templates = signal<SqlTemplate[]>([]);

  load(): void {
    this.http.get<SqlTemplate[]>('/api/console/templates').subscribe(t => {
      this.templates.set(t);
    });
  }
}
```

- [ ] **Step 2: Write component**

```typescript
// frontend/src/app/sql-console/context-sql/context-sql.component.ts
import { ChangeDetectionStrategy, Component, inject, OnInit, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SqlTemplate } from '../../models/fab-query.models';
import { ContextSqlService } from './context-sql.service';

@Component({
  selector: 'app-context-sql',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './context-sql.component.html',
})
export class ContextSqlComponent implements OnInit {
  private svc = inject(ContextSqlService);
  templates = this.svc.templates;
  selected = output<SqlTemplate>();

  ngOnInit(): void {
    this.svc.load();
  }

  onSelect(event: Event): void {
    const id = (event.target as HTMLSelectElement).value;
    const tpl = this.templates().find(t => t.id === id);
    if (tpl) this.selected.emit(tpl);
  }
}
```

```html
<!-- frontend/src/app/sql-console/context-sql/context-sql.component.html -->
<div class="context-sql-selector">
  <label>情境 SQL</label>
  <select (change)="onSelect($event)">
    <option value="">— 選擇範本 —</option>
    @for (tpl of templates(); track tpl.id) {
      <option [value]="tpl.id">{{ tpl.name }}</option>
    }
  </select>
</div>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/sql-console/context-sql/
git commit -m "feat: ContextSqlComponent + service — template selector that fills Monaco editor"
```

---

## Task 22: `SqlConsoleComponent` — Page Container + Routing

**Files:**
- Create: `frontend/src/app/sql-console/sql-console.component.ts`
- Create: `frontend/src/app/sql-console/sql-console.component.html`
- Modify: `frontend/src/app/app.routes.ts`

- [ ] **Step 1: Write page component**

```typescript
// frontend/src/app/sql-console/sql-console.component.ts
import { ChangeDetectionStrategy, Component, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule, FormControl, Validators } from '@angular/forms';
import { FabQueryService } from '../services/fab-query.service';
import { FabResult, SqlTemplate } from '../models/fab-query.models';
import { FabSelectorComponent } from '../shared/fab-selector/fab-selector.component';
import { ResultsComponent } from '../shared/results/results.component';
import { SqlEditorComponent } from './sql-editor/sql-editor.component';
import { NamedParamInputsComponent } from './sql-editor/named-param.directive';
import { ContextSqlComponent } from './context-sql/context-sql.component';

@Component({
  selector: 'app-sql-console',
  standalone: true,
  imports: [
    CommonModule, FormsModule, ReactiveFormsModule,
    FabSelectorComponent, ResultsComponent,
    SqlEditorComponent, NamedParamInputsComponent, ContextSqlComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './sql-console.component.html',
})
export class SqlConsoleComponent {
  private queryService = inject(FabQueryService);

  selectedFabs = signal<string[]>([]);
  sql = signal<string>('');
  rowLimit = signal<number>(100);
  namedParams = signal<Record<string, unknown>>({});
  fabResults = signal<FabResult[]>([]);
  loadingFabs = signal<string[]>([]);
  isExecuting = signal(false);
  executeError = signal<string | null>(null);

  canExecute = computed(() =>
    !this.isExecuting() &&
    this.selectedFabs().length > 0 &&
    this.sql().trim().length > 0 &&
    this.rowLimit() >= 1 &&
    this.rowLimit() <= 300
  );

  onTemplateSelected(tpl: SqlTemplate): void {
    this.sql.set(tpl.sql.trim());
    // Reset named params — directive re-extracts from new SQL
    this.namedParams.set({});
  }

  onParamsChange(params: Record<string, unknown>): void {
    this.namedParams.set(params);
  }

  execute(): void {
    if (!this.canExecute()) return;
    this.isExecuting.set(true);
    this.executeError.set(null);
    this.fabResults.set([]);
    this.loadingFabs.set([...this.selectedFabs()]);

    this.queryService.execute(
      this.sql(), this.selectedFabs(), this.rowLimit(), this.namedParams()
    ).subscribe({
      next: queryId => this.streamResults(queryId),
      error: err => {
        this.executeError.set(err?.error?.error ?? 'Execute failed');
        this.isExecuting.set(false);
        this.loadingFabs.set([]);
      },
    });
  }

  private streamResults(queryId: string): void {
    this.queryService.stream(queryId).subscribe({
      next: event => {
        if ('type' in event && event.type === 'done') {
          this.isExecuting.set(false);
          this.loadingFabs.set([]);
          return;
        }
        const result = event as FabResult;
        this.fabResults.update(prev => [...prev, result]);
        this.loadingFabs.update(prev => prev.filter(f => f !== result.fab));
      },
      error: () => {
        this.executeError.set('SSE connection lost. Please retry.');
        this.isExecuting.set(false);
        this.loadingFabs.set([]);
      },
    });
  }
}
```

```html
<!-- frontend/src/app/sql-console/sql-console.component.html -->
<div class="sql-console">
  <!-- Builder pane (top) -->
  <div class="builder-pane">
    <div class="builder-controls">
      <app-fab-selector [(selected)]="selectedFabs" />

      <label class="rowlimit-field">
        每廠筆數上限
        <input type="number" [value]="rowLimit()" (input)="rowLimit.set(+$any($event.target).value)"
          min="1" max="300" />
        <span class="hint">最大 300</span>
      </label>

      <app-context-sql (selected)="onTemplateSelected($event)" />
    </div>

    <app-sql-editor [(sql)]="sql" />
    <app-named-param-inputs [sql]="sql()" (valuesChange)="onParamsChange($event)" />

    @if (executeError()) {
      <div class="execute-error">{{ executeError() }}</div>
    }

    <button class="execute-btn" (click)="execute()" [disabled]="!canExecute()">
      {{ isExecuting() ? '查詢中…' : '執行' }}
    </button>
  </div>

  <!-- Results pane (bottom) -->
  <div class="results-pane">
    <app-results [results]="fabResults()" [loadingFabs]="loadingFabs()" />
  </div>
</div>
```

- [ ] **Step 2: Add route**

```typescript
// frontend/src/app/app.routes.ts
import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'sql-console', pathMatch: 'full' },
  {
    path: 'sql-console',
    loadComponent: () =>
      import('./sql-console/sql-console.component').then(m => m.SqlConsoleComponent),
  },
];
```

- [ ] **Step 3: Build to check for compilation errors**

```bash
cd frontend && ng build 2>&1 | tail -20
```

Expected: Build successful (0 errors)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/sql-console/ frontend/src/app/app.routes.ts
git commit -m "feat: SqlConsoleComponent — page container with execute flow + routing"
```

---

## Task 23: Docker Compose + Go Dockerfile + Angular Dockerfile

**Files:**
- Create: `backend/Dockerfile`
- Create: `sidecar/Dockerfile`
- Create: `frontend/Dockerfile`
- Modify: `docker-compose.yml`

- [ ] **Step 1: `backend/Dockerfile`**

```dockerfile
FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -o server ./cmd/server

FROM alpine:3.19
WORKDIR /app
COPY --from=builder /app/server .
COPY config/ ./config/
EXPOSE 8080
CMD ["./server"]
```

- [ ] **Step 2: `sidecar/Dockerfile`**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: `frontend/Dockerfile`**

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build -- --configuration production

FROM nginx:alpine
COPY --from=builder /app/dist/browser /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

- [ ] **Step 4: Create `frontend/nginx.conf`**

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://backend:8080;
        proxy_set_header Host $host;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_cache off;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

The `proxy_buffering off` is required for SSE to work through nginx.

- [ ] **Step 5: Commit**

```bash
git add backend/Dockerfile sidecar/Dockerfile frontend/Dockerfile frontend/nginx.conf
git commit -m "feat: Dockerfiles for backend, sidecar, and frontend with nginx SSE proxy"
```

---

## Task 24: Verify Full Stack with Docker Compose

- [ ] **Step 1: Copy `.env.example` to `.env` and fill in test DB credentials**

```bash
cp .env.example .env
# Edit .env with real Oracle test DB credentials
```

- [ ] **Step 2: Start all services**

```bash
docker compose up --build -d
```

Expected: all containers start without exit codes

- [ ] **Step 3: Health check backend**

```bash
curl http://localhost:8080/api/console/templates
```

Expected: JSON array of SQL templates

- [ ] **Step 4: Test SELECT-only rejection**

```bash
curl -X POST http://localhost:8080/api/fabs/query \
  -H "Content-Type: application/json" \
  -d '{"sql":"DELETE FROM cpnt","fabs":["F12A"],"rowLimit":10}'
```

Expected: `{"error":"only SELECT queries are allowed"}`

- [ ] **Step 5: Test full query flow**

```bash
# Execute query (replace F12A with a fab that has a real sidecar running)
RESP=$(curl -s -X POST http://localhost:8080/api/fabs/query \
  -H "Content-Type: application/json" \
  -d '{"sql":"SELECT 1 AS test_col FROM dual","fabs":["F12A"],"rowLimit":5}')
echo $RESP

# Stream results
QUERY_ID=$(echo $RESP | python3 -c "import sys,json; print(json.load(sys.stdin)['queryId'])")
curl -N http://localhost:8080/api/fabs/stream/$QUERY_ID
```

Expected: SSE stream with `fab_result` and `done` events

- [ ] **Step 6: Open browser at http://localhost:4200**

Verify:
- Fab selector shows 14 fabs with all/none toggle
- SQL editor (Monaco) loads with syntax highlight
- Selecting context SQL fills the editor
- Named params render when `:param` in SQL
- Running a query shows streaming skeleton → results
- Diff button highlights differing cells
- Pivot button switches layout

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "feat: docker compose integration — full stack verified"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ 選擇查詢目標廠區 → Task 15 (FabSelector), Task 22 (execute guards)
- ✅ 設定 ROWNUM 上限 → Task 5 (rownum.go), Task 10 (handler validation), Task 22 (rowLimit signal)
- ✅ 自由輸入 SQL → Task 19 (Monaco editor)
- ✅ 選擇情境 SQL 範本 → Task 9 (YAML config), Task 21 (ContextSqlComponent)
- ✅ Named parameters → Task 20 (NamedParamInputsComponent)
- ✅ Test DB 試跑驗證 → Task 6 (testdb.go), Task 10 (handler calls testDB)
- ✅ SSE 串流即時顯示 → Task 7 (engine.go), Task 8 (sse.go), Task 11 (Stream handler), Task 14 (FabQueryService)
- ✅ Flat Table 預設顯示 → Task 16 (FlatTableComponent)
- ✅ Diff 視覺化 → Task 13 (detectDiff), Task 17 (DiffPanelComponent), Task 18 (ResultsComponent)
- ✅ Pivot View → Task 17 (PivotViewComponent)
- ✅ Partial failure (fab error banner) → Task 7 (engine partial), Task 11 (fab_error event), Task 18 (error banner)
- ✅ SSE 連線中斷 → Task 14 (onerror handler), Task 22 (streamResults error branch)
- ✅ QueryId 過期 → Task 11 (TTL check)

**No placeholders found.**

**Type consistency check:**
- `FabResult` defined in `fab-query.models.ts` Task 13, used in Tasks 14, 15, 16, 17, 18, 22 — consistent
- `SqlTemplate` defined in `fab-query.models.ts`, used in Task 21 — consistent
- `fabquery.FabResult` in Go defined in `engine.go` Task 7, used in `handler.go` Task 11 — consistent
- `TestDB` interface in `console/handler.go` satisfies `*TestDBClient` from `testdb.go` — consistent
