# SQL Validator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Go 後端加強 SQL 驗證（SELECT-only + 禁止 `*` column wildcard），並在 Python sidecar 實作對應函式（保留但不接入呼叫鏈）。

**Architecture:** Go 側擴充 `validator.go`，使用自製 token scanner 偵測 wildcard；強化 `ValidateSelectOnly` 以追蹤括號深度，防止 `WITH ... DELETE` 繞過。Python 側使用 sqlparse 實作相同規則但不呼叫。

**Tech Stack:** Go 1.25, Python 3, sqlparse

---

## File Map

| 動作 | 路徑 |
|------|------|
| Modify | `backend/internal/fabquery/validator.go` |
| Modify | `backend/internal/console/handler.go` |
| Modify | `backend/tests/fabquery/validator_test.go` |
| Modify | `sidecar/main.py` |
| Modify | `sidecar/requirements.txt` |
| Modify | `sidecar/tests/test_main.py` |

---

## Task 1: Go — 擴充 validator 測試（先讓它們 fail）

**Files:**
- Modify: `backend/tests/fabquery/validator_test.go`

- [ ] **Step 1: 替換 validator_test.go 內容**

```go
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
		// 合法
		{"SELECT id FROM cpnt", true},
		{"select name FROM sop WHERE id = :id", true},
		{"  \n  SELECT col FROM tbl", true},
		{"WITH cte AS (SELECT 1 FROM dual) SELECT * FROM cte", true},
		{"WITH cte AS (SELECT id FROM cpnt) SELECT id FROM cte", true},
		// 非 SELECT 開頭
		{"INSERT INTO cpnt VALUES (1)", false},
		{"UPDATE cpnt SET name = 'x'", false},
		{"DELETE FROM cpnt", false},
		{"DROP TABLE cpnt", false},
		{"CREATE TABLE x (id NUMBER)", false},
		{"MERGE INTO t USING s ON (t.id=s.id) WHEN MATCHED THEN UPDATE SET t.v=s.v", false},
		// WITH + 非 SELECT 主語句
		{"WITH cte AS (SELECT 1 FROM dual) DELETE FROM cpnt", false},
		{"WITH cte AS (SELECT 1 FROM dual) UPDATE cpnt SET name = 'x'", false},
		{"WITH cte AS (SELECT 1 FROM dual) INSERT INTO cpnt VALUES (1)", false},
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

func TestValidateNoStarColumns(t *testing.T) {
	cases := []struct {
		sql   string
		valid bool
	}{
		// 合法
		{"SELECT id, name FROM cpnt", true},
		{"SELECT price * 2 FROM tbl", true},
		{"SELECT (a+b) * c FROM tbl", true},
		{"SELECT a * b FROM tbl", true},
		{"SELECT ROWNUM * 2 FROM cpnt", true},
		// column wildcard
		{"SELECT * FROM cpnt", false},
		{"SELECT t.* FROM cpnt t", false},
		{"SELECT COUNT(*) FROM cpnt", false},
		{"SELECT *, id FROM cpnt", false},
		// 子查詢
		{"SELECT col FROM (SELECT * FROM tbl)", false},
		// CTE
		{"WITH cte AS (SELECT * FROM t) SELECT id FROM cte", false},
		{"WITH cte AS (SELECT t.* FROM t) SELECT id FROM cte", false},
	}
	for _, c := range cases {
		err := fabquery.ValidateNoStarColumns(c.sql)
		if c.valid && err != nil {
			t.Errorf("expected valid for %q, got: %v", c.sql, err)
		}
		if !c.valid && err == nil {
			t.Errorf("expected invalid for %q, got nil error", c.sql)
		}
	}
}
```

- [ ] **Step 2: 確認測試失敗（`ValidateNoStarColumns` 尚未實作）**

```bash
cd backend && go test ./tests/fabquery/... -run TestValidate -v
```

預期：`TestValidateNoStarColumns` 編譯失敗 `undefined: fabquery.ValidateNoStarColumns`。部分 `TestValidateSelectOnly` 新增的 WITH+DELETE 案例也應該 fail（舊實作只做前綴比對）。

---

## Task 2: Go — 重寫 validator.go

**Files:**
- Modify: `backend/internal/fabquery/validator.go`

- [ ] **Step 1: 以下列內容完整替換 validator.go**

```go
package fabquery

import (
	"fmt"
	"strings"
)

// ValidateSelectOnly rejects non-SELECT statements.
// For WITH-prefixed SQL it traces past all CTE definitions to verify the
// final DML is SELECT, blocking WITH ... DELETE/UPDATE/INSERT bypass.
func ValidateSelectOnly(sql string) error {
	upper := strings.TrimSpace(strings.ToUpper(sql))
	switch {
	case strings.HasPrefix(upper, "SELECT"):
		return nil
	case strings.HasPrefix(upper, "WITH"):
		if dmlAfterWith(sql) == "SELECT" {
			return nil
		}
	}
	return fmt.Errorf("only SELECT queries are allowed")
}

// ValidateNoStarColumns rejects SQL that uses * as a column wildcard.
// Covers SELECT *, t.*, COUNT(*), and wildcards inside subqueries/CTEs.
// Arithmetic multiplication (price * 2) is allowed.
func ValidateNoStarColumns(sql string) error {
	toks := tokenize(sql)
	for i, t := range toks {
		if t != tkStar {
			continue
		}
		var left, right tkind = tkOther, tkOther
		if i > 0 {
			left = toks[i-1]
		}
		if i+1 < len(toks) {
			right = toks[i+1]
		}
		// arithmetic: left produces a value AND right expects a value
		if isLeftVal(left) && isRightVal(right) {
			continue
		}
		return fmt.Errorf("SELECT * is not allowed: use explicit column names")
	}
	return nil
}

// --- token scanner internals ---

type tkind uint8

const (
	tkIdent   tkind = iota // user-defined identifier (column, table, pseudo-column)
	tkKeyword              // SQL reserved word
	tkNumber               // numeric literal
	tkLParen               // (
	tkRParen               // )
	tkDot                  // .
	tkStar                 // *
	tkOther                // comma, other operators, string literals, etc.
)

// sqlKeywords is the set of SQL reserved words that are never value-producing
// and therefore cannot be the LHS of arithmetic *.
var sqlKeywords = map[string]bool{
	"SELECT": true, "FROM": true, "WHERE": true, "AND": true, "OR": true,
	"NOT": true, "IN": true, "IS": true, "AS": true, "ON": true, "BY": true,
	"SET": true, "INTO": true, "DISTINCT": true, "GROUP": true, "ORDER": true,
	"HAVING": true, "UNION": true, "INTERSECT": true, "EXCEPT": true,
	"WITH": true, "JOIN": true, "INNER": true, "LEFT": true, "RIGHT": true,
	"OUTER": true, "FULL": true, "CROSS": true, "USING": true, "CASE": true,
	"WHEN": true, "THEN": true, "ELSE": true, "END": true, "ALL": true,
	"ANY": true, "INSERT": true, "UPDATE": true, "DELETE": true, "MERGE": true,
	"CREATE": true, "DROP": true, "ALTER": true, "TRUNCATE": true,
	"BETWEEN": true, "LIKE": true, "EXISTS": true, "OVER": true,
	"PARTITION": true,
}

func isLeftVal(t tkind) bool  { return t == tkIdent || t == tkNumber || t == tkRParen }
func isRightVal(t tkind) bool { return t == tkIdent || t == tkNumber || t == tkLParen }

// tokenize converts sql into a flat slice of token kinds,
// stripping comments and string literals.
func tokenize(sql string) []tkind {
	var out []tkind
	i, n := 0, len(sql)
	for i < n {
		// whitespace
		if sql[i] <= ' ' {
			i++
			continue
		}
		// line comment: --
		if i+1 < n && sql[i] == '-' && sql[i+1] == '-' {
			for i < n && sql[i] != '\n' {
				i++
			}
			continue
		}
		// block comment: /* */
		if i+1 < n && sql[i] == '/' && sql[i+1] == '*' {
			i += 2
			for i+1 < n && !(sql[i] == '*' && sql[i+1] == '/') {
				i++
			}
			if i+1 < n {
				i += 2
			}
			continue
		}
		// string literal: '...' (Oracle uses '' to escape a literal quote)
		if sql[i] == '\'' {
			i = skipString(sql, i)
			out = append(out, tkOther)
			continue
		}
		// identifier or SQL keyword
		if isIdentStart(sql[i]) {
			j := i
			for j < n && isIdentCh(sql[j]) {
				j++
			}
			word := strings.ToUpper(sql[i:j])
			if sqlKeywords[word] {
				out = append(out, tkKeyword)
			} else {
				out = append(out, tkIdent)
			}
			i = j
			continue
		}
		// number
		if sql[i] >= '0' && sql[i] <= '9' {
			for i < n && (sql[i] >= '0' && sql[i] <= '9' || sql[i] == '.') {
				i++
			}
			out = append(out, tkNumber)
			continue
		}
		// Oracle bind variable: :name → treat as identifier
		if sql[i] == ':' && i+1 < n && isIdentStart(sql[i+1]) {
			i++
			for i < n && isIdentCh(sql[i]) {
				i++
			}
			out = append(out, tkIdent)
			continue
		}
		// single-char tokens
		switch sql[i] {
		case '(':
			out = append(out, tkLParen)
		case ')':
			out = append(out, tkRParen)
		case '.':
			out = append(out, tkDot)
		case '*':
			out = append(out, tkStar)
		default:
			out = append(out, tkOther)
		}
		i++
	}
	return out
}

// dmlAfterWith returns the uppercased DML keyword of the final statement
// in a WITH-prefixed SQL, after tracing past all CTE definitions.
func dmlAfterWith(sql string) string {
	i, n := 4, len(sql) // skip "WITH"
	depth, pastCTE := 0, false

	for i < n {
		i = skipWS(sql, i)
		if i >= n {
			break
		}
		switch {
		case sql[i] == '\'':
			i = skipString(sql, i)
		case sql[i] == '(':
			depth++
			i++
		case sql[i] == ')':
			depth--
			if depth == 0 {
				pastCTE = true
			}
			i++
		case sql[i] == ',' && depth == 0:
			pastCTE = false
			i++
		case isIdentStart(sql[i]):
			j := i
			for j < n && isIdentCh(sql[j]) {
				j++
			}
			if depth == 0 && pastCTE {
				return strings.ToUpper(sql[i:j])
			}
			i = j
		default:
			i++
		}
	}
	return ""
}

func skipWS(sql string, i int) int {
	for i < len(sql) {
		switch {
		case sql[i] <= ' ':
			i++
		case i+1 < len(sql) && sql[i] == '-' && sql[i+1] == '-':
			for i < len(sql) && sql[i] != '\n' {
				i++
			}
		case i+1 < len(sql) && sql[i] == '/' && sql[i+1] == '*':
			i += 2
			for i+1 < len(sql) && !(sql[i] == '*' && sql[i+1] == '/') {
				i++
			}
			if i+1 < len(sql) {
				i += 2
			}
		default:
			return i
		}
	}
	return i
}

func skipString(sql string, i int) int {
	i++ // skip opening '
	for i < len(sql) {
		if sql[i] == '\'' {
			i++
			if i < len(sql) && sql[i] == '\'' {
				i++ // escaped ''
				continue
			}
			break
		}
		i++
	}
	return i
}

func isIdentStart(c byte) bool {
	return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_'
}

func isIdentCh(c byte) bool {
	return isIdentStart(c) || (c >= '0' && c <= '9') || c == '$' || c == '#'
}
```

- [ ] **Step 2: 執行測試**

```bash
cd backend && go test ./tests/fabquery/... -run TestValidate -v
```

預期：`TestValidateSelectOnly` 和 `TestValidateNoStarColumns` 所有案例全數通過。

- [ ] **Step 3: 確認 build 無誤**

```bash
cd backend && go build ./...
```

預期：無輸出（編譯成功）。

---

## Task 3: Go — 在 handler.go 加入 ValidateNoStarColumns 呼叫

**Files:**
- Modify: `backend/internal/console/handler.go`

- [ ] **Step 1: 在 ValidateSelectOnly 呼叫之後加入 ValidateNoStarColumns**

找到以下區塊（約 80–83 行）：

```go
	if err := fabquery.ValidateSelectOnly(req.SQL); err != nil {
		writeJSON(w, 400, errorResponse{err.Error()})
		return
	}
	if len(req.Fabs) == 0 {
```

替換為：

```go
	if err := fabquery.ValidateSelectOnly(req.SQL); err != nil {
		writeJSON(w, 400, errorResponse{err.Error()})
		return
	}
	if err := fabquery.ValidateNoStarColumns(req.SQL); err != nil {
		writeJSON(w, 400, errorResponse{err.Error()})
		return
	}
	if len(req.Fabs) == 0 {
```

- [ ] **Step 2: 執行 handler 測試**

```bash
cd backend && go test ./tests/console/... -v
```

預期：既有的 handler 測試全數通過（無回歸）。

- [ ] **Step 3: 執行全套測試並 commit**

```bash
cd backend && go test ./... -v
```

預期：所有測試通過。

```bash
git add backend/internal/fabquery/validator.go \
        backend/internal/console/handler.go \
        backend/tests/fabquery/validator_test.go
git commit -m "feat: strengthen ValidateSelectOnly + add ValidateNoStarColumns"
```

---

## Task 4: Python — 加入 sqlparse 依賴

**Files:**
- Modify: `sidecar/requirements.txt`

- [ ] **Step 1: 在 requirements.txt 末尾加入 sqlparse**

```
fastapi==0.111.0
uvicorn==0.30.0
cx_Oracle==8.3.0
pydantic==2.7.0
pytest==8.2.0
httpx==0.27.0
sqlparse==0.5.0
```

- [ ] **Step 2: 安裝確認**

```bash
cd sidecar && pip install sqlparse==0.5.0
```

預期：Successfully installed sqlparse-0.5.0（或已安裝）。

---

## Task 5: Python — 實作 validator 函式（不接入呼叫鏈）

**Files:**
- Modify: `sidecar/main.py`

- [ ] **Step 1: 在 main.py 頂部加入 import**

在現有 `import os` 之後加入：

```python
import sqlparse
from sqlparse import tokens as T
```

- [ ] **Step 2: 在 `app = FastAPI(lifespan=lifespan)` 之前加入以下函式**

```python
def validate_select_only(sql: str) -> str | None:
    """返回 error message，合法時返回 None。不接入呼叫鏈，保留供未來使用。"""
    upper = sql.strip().upper()
    if upper.startswith("SELECT"):
        return None
    if upper.startswith("WITH"):
        if _dml_after_with(sql) == "SELECT":
            return None
    return "only SELECT queries are allowed"


def validate_no_star(sql: str) -> str | None:
    """偵測 column wildcard (*, t.*)，返回 error message，合法時返回 None。
    不接入呼叫鏈，保留供未來使用。"""
    for stmt in sqlparse.parse(sql):
        for token in stmt.flatten():
            if token.ttype is T.Wildcard:
                return "SELECT * is not allowed: use explicit column names"
    return None


def _dml_after_with(sql: str) -> str:
    """掃描 WITH ... AS (...) CTE 定義後的主 DML keyword（大寫）。"""
    i, n = 4, len(sql)  # skip "WITH"
    depth, past_cte = 0, False
    while i < n:
        i = _skip_ws_comments(sql, i)
        if i >= n:
            break
        c = sql[i]
        if c == "'":
            i = _skip_string(sql, i)
        elif c == "(":
            depth += 1
            i += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                past_cte = True
            i += 1
        elif c == "," and depth == 0:
            past_cte = False
            i += 1
        elif c.isalpha() or c == "_":
            j = i
            while j < n and (sql[j].isalnum() or sql[j] in ("_", "$", "#")):
                j += 1
            if depth == 0 and past_cte:
                return sql[i:j].upper()
            i = j
        else:
            i += 1
    return ""


def _skip_ws_comments(sql: str, i: int) -> int:
    n = len(sql)
    while i < n:
        if sql[i] in " \t\n\r":
            i += 1
        elif i + 1 < n and sql[i : i + 2] == "--":
            while i < n and sql[i] != "\n":
                i += 1
        elif i + 1 < n and sql[i : i + 2] == "/*":
            i += 2
            while i + 1 < n and sql[i : i + 2] != "*/":
                i += 1
            if i + 1 < n:
                i += 2
        else:
            break
    return i


def _skip_string(sql: str, i: int) -> int:
    i += 1  # skip opening '
    while i < len(sql):
        if sql[i] == "'":
            i += 1
            if i < len(sql) and sql[i] == "'":
                i += 1  # escaped ''
                continue
            break
        i += 1
    return i
```

- [ ] **Step 3: 確認現有測試不受影響**

```bash
cd sidecar && python -m pytest tests/ -v
```

預期：`test_query_returns_rows`、`test_query_db_error_returns_400`、`test_health_ok` 全數通過。

---

## Task 6: Python — 撰寫 validator 測試

**Files:**
- Modify: `sidecar/tests/test_main.py`

- [ ] **Step 1: 在 test_main.py 末尾加入以下測試**

```python
# --- validate_select_only ---

with patch.dict("sys.modules", {"cx_Oracle": MagicMock(SessionPool=MagicMock(return_value=mock_pool))}):
    from main import validate_select_only, validate_no_star  # noqa: E402


def test_validate_select_only_valid():
    assert validate_select_only("SELECT id FROM cpnt") is None
    assert validate_select_only("select name FROM sop WHERE id = :id") is None
    assert validate_select_only("  \n  SELECT col FROM tbl") is None
    assert validate_select_only("WITH cte AS (SELECT 1 FROM dual) SELECT * FROM cte") is None
    assert validate_select_only("WITH cte AS (SELECT id FROM cpnt) SELECT id FROM cte") is None


def test_validate_select_only_invalid():
    assert validate_select_only("INSERT INTO cpnt VALUES (1)") is not None
    assert validate_select_only("UPDATE cpnt SET name = 'x'") is not None
    assert validate_select_only("DELETE FROM cpnt") is not None
    assert validate_select_only("DROP TABLE cpnt") is not None
    assert validate_select_only("WITH cte AS (SELECT 1 FROM dual) DELETE FROM cpnt") is not None
    assert validate_select_only("WITH cte AS (SELECT 1 FROM dual) UPDATE cpnt SET name = 'x'") is not None
    assert validate_select_only("WITH cte AS (SELECT 1 FROM dual) INSERT INTO cpnt VALUES (1)") is not None


# --- validate_no_star ---

def test_validate_no_star_valid():
    assert validate_no_star("SELECT id, name FROM cpnt") is None
    assert validate_no_star("SELECT price * 2 FROM tbl") is None
    assert validate_no_star("SELECT (a+b) * c FROM tbl") is None
    assert validate_no_star("SELECT a * b FROM tbl") is None


def test_validate_no_star_invalid():
    assert validate_no_star("SELECT * FROM cpnt") is not None
    assert validate_no_star("SELECT t.* FROM cpnt t") is not None
    assert validate_no_star("SELECT COUNT(*) FROM cpnt") is not None
    assert validate_no_star("SELECT *, id FROM cpnt") is not None
    assert validate_no_star("SELECT col FROM (SELECT * FROM tbl)") is not None
    assert validate_no_star("WITH cte AS (SELECT * FROM t) SELECT id FROM cte") is not None
    assert validate_no_star("WITH cte AS (SELECT t.* FROM t) SELECT id FROM cte") is not None
```

- [ ] **Step 2: 執行全套 Python 測試**

```bash
cd sidecar && python -m pytest tests/ -v
```

預期：所有測試通過（包含新增的 validator 測試）。

- [ ] **Step 3: Commit**

```bash
git add sidecar/main.py sidecar/requirements.txt sidecar/tests/test_main.py
git commit -m "feat: add SQL validators to sidecar (reserved, not wired)"
```

---

## Self-Review

**Spec coverage check:**
- ✅ `ValidateSelectOnly` 強化（WITH+DELETE 防繞過）
- ✅ `ValidateNoStarColumns` 新增（`*`、`t.*`、`COUNT(*)`、子查詢、CTE）
- ✅ handler.go 接入 `ValidateNoStarColumns`
- ✅ Python `validate_select_only` + `validate_no_star` 實作
- ✅ Python 不接入 `/query` endpoint
- ✅ Go 測試覆蓋所有討論案例
- ✅ Python 測試覆蓋所有討論案例

**Type/method consistency:**
- `fabquery.ValidateSelectOnly` — Task 1 測試 → Task 2 實作 → Task 3 呼叫 ✅
- `fabquery.ValidateNoStarColumns` — Task 1 測試 → Task 2 實作 → Task 3 呼叫 ✅
- `validate_select_only` / `validate_no_star` — Task 5 實作 → Task 6 測試 ✅
