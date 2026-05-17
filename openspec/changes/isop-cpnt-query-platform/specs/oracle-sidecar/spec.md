## ADDED Requirements

### Requirement: 接收並執行 SQL 查詢請求
Sidecar 服務 SHALL 提供 HTTP endpoint 接收來自後端的 SQL 查詢請求，使用 Oracle SDK 執行查詢，並回傳結果。

#### Scenario: 成功執行查詢
- **WHEN** 後端發送合法的 SQL 查詢請求（含 SQL 字串與參數）
- **THEN** Sidecar SHALL 執行查詢並以 JSON 格式回傳查詢結果列表

#### Scenario: SQL 語法錯誤
- **WHEN** 後端發送語法有誤的 SQL
- **THEN** Sidecar SHALL 回傳 HTTP 400 及錯誤描述，不執行查詢

#### Scenario: Oracle DB 連線失敗
- **WHEN** Oracle DB 無法連線（網路問題或 DB 下線）
- **THEN** Sidecar SHALL 回傳 HTTP 503 並附上錯誤說明

### Requirement: 支援 Named Parameter 綁定
Sidecar SHALL 支援 Oracle 風格的 named parameters（`:param_name`）以防止 SQL injection。

#### Scenario: 使用 Named Parameters 查詢
- **WHEN** 後端發送包含 named parameters 的 SQL 與對應參數值 dict
- **THEN** Sidecar SHALL 正確綁定參數後執行查詢，回傳結果

#### Scenario: 拒絕字串拼接 SQL
- **WHEN** SQL 中包含使用者輸入值直接拼接（無 named parameter）
- **THEN** 此情況由後端責任避免；Sidecar 本身不做額外過濾，但 document 明確要求後端必須使用 named parameters

### Requirement: Health Check Endpoint
Sidecar SHALL 提供 health check endpoint 供 Kubernetes liveness probe 使用。

#### Scenario: 服務正常時的 Health Check
- **WHEN** Kubernetes 或後端呼叫 `GET /health`
- **THEN** Sidecar SHALL 回傳 HTTP 200 及 `{"status": "ok"}`

#### Scenario: Oracle DB 無法連線時的 Health Check
- **WHEN** Sidecar 無法連線 Oracle DB 時收到 `GET /health`
- **THEN** Sidecar SHALL 回傳 HTTP 503 及 `{"status": "unhealthy", "reason": "db_unreachable"}`

### Requirement: 查詢 Timeout 控制
Sidecar SHALL 對每個 Oracle 查詢設定最長執行時間，超時時回傳錯誤以避免請求堆積。

#### Scenario: 查詢在 Timeout 內完成
- **WHEN** Oracle 查詢在 10 秒內完成
- **THEN** Sidecar SHALL 正常回傳結果

#### Scenario: 查詢超過 Timeout
- **WHEN** Oracle 查詢執行超過 10 秒
- **THEN** Sidecar SHALL 中止查詢並回傳 HTTP 504 及 `{"error": "QUERY_TIMEOUT"}`
