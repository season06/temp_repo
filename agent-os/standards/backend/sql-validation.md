# SQL Validation

## SELECT-Only Enforcement

所有 SQL 在執行前必須通過 `fabquery.ValidateSelectOnly(sql)` 驗證。

- 只允許 `SELECT` 與 `WITH...SELECT` 語句
- 非 SELECT 回傳 400，不進入 Test DB 試跑

## 現有實作限制（已知 TODO）

`validator.go` 使用 prefix 策略，存在已知繞過風險：

```go
// TODO - SQL linter (find suitable golang package)
// 已知限制：WITH cte AS (DELETE ...) 可通過驗證
func ValidateSelectOnly(sql string) error {
    upper := strings.TrimSpace(strings.ToUpper(sql))
    if strings.HasPrefix(upper, "SELECT") || strings.HasPrefix(upper, "WITH") {
        return nil
    }
    return fmt.Errorf("only SELECT queries are allowed")
}
```

**修正方向（待評估）：**
- Token scanner：在 prefix 通過後，對全文進行 DML 關鍵字 regex 掃描
- Go SQL parser：`xwb1989/sqlparser`（MySQL dialect，非 Oracle，需評估相容性）
- Oracle 無開源 Go AST parser，選用前需確認方言覆蓋率

## 驗證時機

```
POST /api/fabs/query
  ├─ ValidateSelectOnly()   ← 第一關，語法層面
  ├─ WrapWithRownum()
  └─ TestDBClient.TryRun()  ← 第二關，實際執行試跑
```

前端不可信，所有驗證必須在後端完成。

## Fab 名稱驗證

請求中的 `fabs[]` 必須對照 `config.ValidFabs` 白名單，未知廠區回傳 400。
