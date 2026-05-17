# SSE Streaming Pattern

## 架構

SQL Console 使用兩階段 API 實現多廠串流：

```
POST /api/fabs/query       → 回傳 queryId（驗證 + 試跑完成後）
GET  /api/fabs/stream/{id} → SSE 連線，逐廠推送結果
```

兩階段設計原因：驗證失敗在 POST 即早回傳 400，不需建立 SSE 連線。

## Query Store

`sync.Map` 暫存已驗證的查詢，TTL 5 分鐘：

```go
h.store.Store(queryID, storedQuery{
    wrappedSQL:  wrappedSQL,
    fabs:        req.Fabs,
    namedParams: req.NamedParams,
    expiresAt:   time.Now().Add(5 * time.Minute),
})
```

- TTL 到期的查詢在 Stream 存取時懶刪除（回傳 404）
- 未被 stream 存取的查詢永遠不會主動清除（已知限制）

## Fan-Out 模式

`fabquery.Engine` 對每個 fab 啟動獨立 goroutine，結果透過 channel 收集：

```go
ch := engine.Execute(ctx, sql, fabs, params)
for result := range ch {  // channel 關閉即結束
    writeSSEEvent(w, result)
}
writeSSEEvent(w, "done", ...)
```

- 每個 goroutine 有獨立 30s timeout（per fab）
- 單一 fab 失敗不中斷其他 fab（部分失敗模式）
- 失敗 fab 發出 `fab_error` event，成功 fab 發出 `fab_result` event

## SSE Event 格式

```
event: fab_result
data: {"fab":"F12A","columns":[...],"rows":[...],"status":"ok"}

event: fab_error
data: {"fab":"F12B","message":"ORA-00942: ..."}

event: done
data: {"status":"complete"}
```

## SSE Headers

```go
fabquery.SetSSEHeaders(w)  // Content-Type: text/event-stream, no-cache, keep-alive
```

不要在 stream endpoint 設定 `Access-Control-Allow-Origin: *`（需依部署環境限制來源）。
