## Why

iSOP 系統分佈於 14 個廠區，team members 目前缺乏統一介面查詢各廠的 API 設定（Cpnt）與 SOP 運行結果，只能土法煉鋼逐廠查詢，耗時且易出錯。建立此平台可將跨廠查詢整合為一站式操作，大幅提升排障與日常管理效率。

## What Changes

- **新建前端 Angular 應用**：提供跨廠 SOP 搜尋、Cpnt 搜尋、執行失敗 Cpnt 搜尋三個核心頁面
- **新建後端 Golang API 服務**：提供 RESTful 查詢端點，封裝跨廠資料存取邏輯
- **新建 Python Sidecar Adapter**：橋接公司內部 Oracle SDK，開放 HTTP 端口供後端呼叫
- **新建容器化部署設定**：Docker Compose（本地開發）與 Kubernetes manifests（生產環境）
- 所有查詢以 plain SQL 方式存取 Oracle DB，不引入 ORM

## Capabilities

### New Capabilities
<!-- 以下三項為日後新增，不在本次範圍內
- `sop-search`：跨廠 SOP 搜尋 — 使用者可依廠區、SOP 名稱/ID 篩選並瀏覽 SOP 清單與詳情
- `cpnt-search`：跨廠 Cpnt 搜尋 — 使用者可依廠區、Cpnt 名稱搜尋各廠的 API 積木設定
- `failed-cpnt-search`：失敗 Cpnt 查詢 — 搜尋執行失敗的 Cpnt 記錄並關聯其所屬 SOP，供排障使用
-->
- `oracle-sidecar`：Oracle DB Sidecar Adapter — Python 服務作為 Oracle SDK 橋接層，接收 SQL 查詢請求並回傳結果
- `sql-console`：SQL Console — 使用者可自由輸入或選擇情境 SQL，對選定廠區並行查詢，以 SSE 串流即時顯示各廠結果，支援跨廠 Diff 與 Pivot 視覺化

### Modified Capabilities

## Impact

- **新增服務**：Angular frontend、Golang backend、Python sidecar（三個獨立容器）
- **外部相依**：公司 Oracle DB（唯讀存取特定 tables）
- **網路**：sidecar 與 backend 在同一 pod/network 內通訊；frontend 透過 HTTP API 呼叫 backend
- **資料**：僅讀取，不寫入 Oracle DB
