# Backend Conventions (Golang)

## Project Structure
```
/cmd/server    # 入口點 (main.go)，路由 wiring
/internal      # 核心業務邏輯
  /config        # AppConfig（env var 讀取、ValidFabs 清單）
  /fabquery      # 多廠查詢共用 package（engine、validator、rownum、testdb、sse）
  /console       # SQL Console 專屬 handlers（handler.go、templates.go）
/config        # YAML 設定檔（context_sqls.yaml）
/tests         # 測試檔案
  /fabquery/
  /console/
```

多廠功能共用邏輯放 `/internal/fabquery`，功能專屬邏輯放對應 `/internal/<feature>` package。

## Naming
- 檔案名稱：snake_case（`cpnt_handler.go`）
- 函式/方法：PascalCase（exported）、camelCase（unexported）
- 常數：全大寫 snake_case（`MAX_PAGE_LIMIT`）

## Sidecar Client
- 每個 fab 對應一個獨立 Python sidecar（HTTP POST `/query`）
- URL 從環境變數讀取（`SIDECAR_<FAB>_URL`），透過 `AppConfig.SidecarURLs` map 存取
- 多廠查詢使用 `fabquery.Engine`，goroutine fan-out，per-fab 30s timeout
- Test DB 使用 `fabquery.TestDBClient`，5s timeout
- 使用 `context` 傳遞 timeout，不直接使用 `time.Sleep`

## Error Handling
- 使用 `fmt.Errorf("操作描述: %w", err)` wrapping
- handler 層統一轉換為 HTTP error response
- 不在 service 層直接寫 HTTP response

## SQL 規範
- 所有 SQL 為 plain SQL，不使用 ORM
- SQL 字串定義為 package-level const 或 var
- 使用具名參數（Oracle 風格 `:param_name`）

## Configuration
- 所有設定從環境變數讀取
- 使用 struct tag 對應設定項目
- 敏感設定（DB 連線資訊）不寫入程式碼
