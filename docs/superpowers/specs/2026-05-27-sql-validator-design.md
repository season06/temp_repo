# SQL Validator 設計文件

**日期：** 2026-05-27  
**分支：** sdd

---

## 背景與目標

系統透過 Go 後端接收使用者輸入的 SQL，經由 Python sidecar proxy 送往 Oracle DB 執行。  
目前只有基本的 SELECT-only 前綴驗證，存在兩個漏洞：

1. `WITH ... DELETE/UPDATE/INSERT` 可繞過前綴檢查
2. 未禁止 `SELECT *` / `t.*` / `COUNT(*)` 等全選 column 的寫法

目標：在 Go 後端補強驗證邏輯，Python sidecar 實作對應函式（保留但暫不接入呼叫鏈）。

---

## 合法 SQL 條件

| 規則 | 說明 |
|------|------|
| 只允許查詢 | 最終 DML 必須是 SELECT（含 `WITH` CTE 後接 SELECT） |
| 禁止 `*` 作為 column wildcard | `SELECT *`、`t.*`、`COUNT(*)` 均禁止 |
| 算術乘法放行 | `price * 2`、`(a+b) * c` 不受影響 |

---

## 架構

```
POST /api/fabs/query
       │
       ▼
  Go 後端 validator.go
  ① ValidateSelectOnly      ← 強化：WITH 後需追蹤括號深度確認最終 DML 為 SELECT
  ② ValidateNoStarColumns   ← 新增：token scanner 偵測 column wildcard
       │ 通過
       ▼
  handler.go 繼續處理（WrapWithRownum → TestDB dry-run → store）
       │
       ▼
  Python sidecar /query
  validate_select_only / validate_no_star  ← 實作但不呼叫（保留供未來使用）
       │
       ▼
  cx_Oracle 執行
```

---

## Go — `validator.go`

### ① `ValidateSelectOnly`（強化現有）

**現有問題：** 只做前綴比對，`WITH cte AS (...) DELETE FROM t` 可通過。

**強化邏輯：**
- SQL 前綴為 `SELECT` → 直接通過
- SQL 前綴為 `WITH` → 追蹤括號深度，跳過所有 CTE 定義，找出最終 DML keyword
  - 最終為 `SELECT` → 通過
  - 最終為其他（`DELETE` / `UPDATE` / `INSERT` / `MERGE` 等）→ 拒絕
- 其他前綴 → 拒絕

括號深度追蹤需跳過：
- `--` 行註解
- `/* */` 區塊註解
- `'...'` 字串字面值（避免誤計括號）

### ② `ValidateNoStarColumns`（新增）

**邏輯：** token scanner，逐字元掃描 SQL，回傳第一個違規的 error。

**Token 類型：**
```
ident    — 識別字（字母、數字、_、$）
number   — 數字字面值
lparen   — (
rparen   — )
dot      — .
star     — *
other    — 其餘（逗號、運算子、關鍵字等）
```

**`*` 的判斷規則：**

| 左側 token | 右側 token | 判定 |
|-----------|-----------|------|
| ident / number / rparen | ident / number / lparen | 算術乘法 → 放行 |
| dot | 任意 | column wildcard → 拒絕（`t.*`） |
| 其餘 | 任意 | column wildcard → 拒絕 |

掃描時同樣跳過 `--`、`/* */`、`'...'`，確保不誤判。

**呼叫點：** `handler.go` `Execute()` 中，`ValidateSelectOnly` 之後立即呼叫。

---

## Python — `sidecar/main.py`

使用 `sqlparse`（加入 `requirements.txt`）實作兩個 standalone 函式：

```python
def validate_select_only(sql: str) -> str | None:
    """回傳 error message，合法時回傳 None。"""

def validate_no_star(sql: str) -> str | None:
    """偵測 T.Wildcard token，回傳 error message，合法時回傳 None。"""
```

`/query` endpoint **不呼叫**這兩個函式，保留供未來啟用。

---

## 測試案例

### Go — `tests/fabquery/validator_test.go`

#### `ValidateSelectOnly`

| SQL | 預期 |
|-----|------|
| `SELECT id FROM cpnt` | 通過 |
| `select name FROM sop WHERE id = :id` | 通過 |
| `  \n  SELECT col FROM tbl` | 通過（前置空白） |
| `WITH cte AS (SELECT 1 FROM dual) SELECT * FROM cte` | 通過 |
| `WITH cte AS (SELECT id FROM cpnt) SELECT id FROM cte` | 通過 |
| `INSERT INTO cpnt VALUES (1)` | 拒絕 |
| `UPDATE cpnt SET name = 'x'` | 拒絕 |
| `DELETE FROM cpnt` | 拒絕 |
| `DROP TABLE cpnt` | 拒絕 |
| `MERGE INTO t USING s ON ...` | 拒絕 |
| `WITH cte AS (SELECT 1 FROM dual) DELETE FROM cpnt` | 拒絕 |
| `WITH cte AS (SELECT 1 FROM dual) UPDATE cpnt SET name = 'x'` | 拒絕 |
| `WITH cte AS (SELECT 1 FROM dual) INSERT INTO cpnt VALUES (1)` | 拒絕 |

#### `ValidateNoStarColumns`

| SQL | 預期 |
|-----|------|
| `SELECT id, name FROM cpnt` | 通過 |
| `SELECT price * 2 FROM tbl` | 通過（算術） |
| `SELECT (a+b) * c FROM tbl` | 通過（算術） |
| `SELECT a * b FROM tbl` | 通過（算術） |
| `SELECT *` | 拒絕 |
| `SELECT t.* FROM cpnt t` | 拒絕 |
| `SELECT COUNT(*) FROM cpnt` | 拒絕 |
| `SELECT *, id FROM cpnt` | 拒絕 |
| `SELECT col FROM (SELECT * FROM tbl)` | 拒絕（子查詢） |
| `WITH cte AS (SELECT * FROM t) SELECT id FROM cte` | 拒絕（CTE） |
| `WITH cte AS (SELECT t.* FROM t) SELECT id FROM cte` | 拒絕（CTE + table-qualified） |

### Python — `sidecar/tests/test_main.py`

相同案例集，針對 `validate_select_only` 與 `validate_no_star` 各自測試。

---

## 不在範圍內

- 修改 sidecar `/query` endpoint 的呼叫邏輯
- 驗證 SQL 語意正確性（column 是否存在、型別是否合法等）
- 白名單機制
