# API Conventions

## URL Design
```
GET  /api/fabs/:fab/sops           # 查詢指定廠區的 SOP 清單
GET  /api/fabs/:fab/sops/:id       # 查詢單一 SOP 詳情
GET  /api/fabs/:fab/cpnts          # 查詢指定廠區的 Cpnt 清單
GET  /api/fabs/:fab/cpnts/:id      # 查詢單一 Cpnt 詳情
GET  /api/fabs/:fab/cpnts/failed   # 查詢執行失敗的 Cpnt

# SQL Console（多廠查詢）
POST /api/fabs/query               # 驗證 SQL，回傳 queryId
GET  /api/fabs/stream/{id}         # SSE 串流，逐廠推送結果
GET  /api/console/templates        # 取得情境 SQL 範本清單
GET  /swagger/index.html           # Swagger UI
```
- URL 使用小寫 kebab-case
- 資源名稱使用複數
- `:fab` 路徑參數對應廠區代號（如 `F12A`）

## Request
- 搜尋條件以 query string 傳遞：`?name=xxx&sop_id=yyy`
- 分頁：`?page=1&limit=20`（預設 limit=20，最大 100）

## Response Format
```json
{
  "data": [...],
  "total": 100,
  "page": 1,
  "limit": 20
}
```
錯誤回應：
```json
{
  "error": "FAB_NOT_FOUND",
  "message": "廠區 F99 不存在"
}
```

## HTTP Status Codes
| 情況 | Status |
|------|--------|
| 成功查詢 | 200 |
| 廠區不存在 | 404 |
| 參數錯誤 | 400 |
| Sidecar 無回應 | 502 |
| 內部錯誤 | 500 |

## SSE Response Format（多廠串流）

```
event: fab_result
data: {"fab":"F12A","columns":[...],"rows":[...],"status":"ok"}

event: fab_error
data: {"fab":"F12B","message":"ORA-00942: ..."}

event: done
data: {"status":"complete"}
```

## Sidecar Communication
- 後端呼叫 sidecar 使用 HTTP（內部 port）
- 單廠 timeout：30s（streaming fan-out），5s（Test DB 試跑）
- Sidecar 回傳原始查詢結果，後端負責轉換格式
- 單一 fab 失敗不中斷其他 fab（部分失敗模式）
