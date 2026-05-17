## 1. 專案骨架與基礎建設

- [ ] 1.1 建立 monorepo 目錄結構：`frontend/`、`backend/`、`sidecar/`
- [ ] 1.2 撰寫 `docker-compose.yml`：定義 frontend、backend、sidecar 三個 service
- [ ] 1.3 建立各服務的基礎 `Dockerfile`（frontend、backend、sidecar）
- [ ] 1.4 設定環境變數範本 `.env.example`（Oracle 連線資訊、sidecar port 等）

## 2. Python Sidecar（Oracle Adapter）

- [ ] 2.1 初始化 Python 專案：`pyproject.toml` / `requirements.txt`，安裝 Oracle SDK 與 FastAPI
- [ ] 2.2 實作 `POST /query` endpoint：接收 SQL 字串與 named parameters dict，回傳查詢結果 JSON
- [ ] 2.3 實作 Oracle named parameter 綁定邏輯，確保 `:param_name` 正確替換
- [ ] 2.4 實作 10 秒查詢 timeout 機制，超時回傳 HTTP 504
- [ ] 2.5 實作 `GET /health` endpoint：正常回 200，DB 無法連線回 503
- [ ] 2.6 撰寫 sidecar 單元測試（mock Oracle SDK）：成功查詢、timeout、DB 連線失敗情境
- [ ] 2.7 驗證 sidecar 在 Docker 容器內可正確連線 Oracle DB（需真實 Oracle 連線測試）

## 3. Golang 後端 API

- [ ] 3.1 初始化 Go module，建立 `/cmd`、`/internal/{handler,service,sidecar,model}` 目錄
- [ ] 3.2 實作 `SidecarClient`：封裝對 sidecar HTTP endpoint 的呼叫，含 timeout 與錯誤處理
- [ ] 3.3 定義資料模型：`SopSummary`、`SopDetail`、`CpntSummary`、`CpntDetail`、`FailedCpnt`
- [ ] 3.4 實作 SOP 查詢 service 與 SQL：`GET /api/fabs/:fab/sops`（清單 + 分頁）
- [ ] 3.5 實作 SOP 詳情 service 與 SQL：`GET /api/fabs/:fab/sops/:id`（含關聯 Cpnt）
- [ ] 3.6 實作 Cpnt 查詢 service 與 SQL：`GET /api/fabs/:fab/cpnts`（清單 + 分頁）
- [ ] 3.7 實作 Cpnt 詳情 service 與 SQL：`GET /api/fabs/:fab/cpnts/:id`（含關聯 SOP）
- [ ] 3.8 實作失敗 Cpnt 查詢 service 與 SQL：`GET /api/fabs/:fab/cpnts/failed`（含時間範圍篩選 + 分頁）
- [ ] 3.9 實作 Fab 驗證 middleware：無效 Fab 代號回傳 404
- [ ] 3.10 實作統一錯誤回應格式（`{"error": "CODE", "message": "..."}`）
- [ ] 3.11 撰寫 handler 單元測試（mock SidecarClient）：各 endpoint 的正常與錯誤情境

## 4. Angular 前端

- [ ] 4.1 使用 Angular CLI 初始化專案，設定 standalone component 模式
- [ ] 4.2 建立 `shared/fab-selector` 元件：下拉選單列出 14 個有效廠區
- [ ] 4.3 建立 `shared/pagination` 元件：通用分頁控制項
- [ ] 4.4 建立 `shared/empty-state` 元件：查無資料時的提示訊息
- [ ] 4.5 建立 `CpntService`、`SopService` 封裝後端 API 呼叫
- [ ] 4.6 定義 TypeScript interfaces：`SopSummary`、`SopDetail`、`CpntSummary`、`CpntDetail`、`FailedCpnt`、`Fab`
- [ ] 4.7 實作 SOP 搜尋頁面：廠區選擇 + 關鍵字輸入 + 結果清單（含分頁）
- [ ] 4.8 實作 SOP 詳情頁面：顯示 SOP 完整資訊與關聯 Cpnt 清單
- [ ] 4.9 實作 Cpnt 搜尋頁面：廠區選擇 + 關鍵字輸入 + 結果清單（含分頁）
- [ ] 4.10 實作 Cpnt 詳情頁面：顯示 Cpnt 設定詳情與關聯 SOP 清單
- [ ] 4.11 實作失敗 Cpnt 查詢頁面：廠區選擇 + 時間範圍篩選 + 結果清單（含分頁與 SOP 連結）
- [ ] 4.12 設定 Angular routing：三個主頁面 + 詳情頁
- [ ] 4.13 撰寫核心元件的單元測試（使用 mock service）

## 5. 部署設定

- [ ] 5.1 建立 Kubernetes Deployment manifest：backend + sidecar 同 Pod，frontend 獨立 Pod
- [ ] 5.2 建立 Kubernetes Service manifest（ClusterIP for backend/sidecar，NodePort/LoadBalancer for frontend）
- [ ] 5.3 建立 Kubernetes Ingress manifest：frontend 與 backend API 的路由規則
- [ ] 5.4 建立 Kubernetes ConfigMap / Secret 範本：Oracle 連線設定
- [ ] 5.5 設定後端 Kubernetes liveness probe 呼叫 sidecar `/health`

## 6. SQL Console 設定

- [ ] 6.1 建立 `config/context_sqls.yaml`：定義情境 SQL 資料結構（id、name、description、sql、params）
- [ ] 6.2 撰寫初始情境 SQL 範本（至少 2–3 個常用查詢，如失敗 Cpnt、孤兒 Cpnt 等）
- [ ] 6.3 後端實作 config loader：啟動時讀取 YAML，驗證欄位完整性，暴露為 `GET /api/sql/templates`
- [ ] 6.4 後端單元測試：config 缺少必要欄位時啟動失敗並輸出清楚錯誤訊息

## 7. SQL Console 後端

- [ ] 7.1 實作 SQL SELECT-only 驗證：使用 parser library 檢查 top-level statement type，非 SELECT 回傳 400
- [ ] 7.2 實作 ROWNUM wrap：後端自動將使用者 SQL 包裹 `SELECT * FROM (...) WHERE ROWNUM <= :limit`
- [ ] 7.3 實作 Test DB 試跑：將 wrapped SQL 送 Test DB sidecar，超時回傳錯誤，通過才繼續
- [ ] 7.4 實作 `POST /api/sql/execute`：接收 SQL、params、fabs、rowLimit，驗證後建立 execution，回傳 `execution_id`
- [ ] 7.5 實作 `GET /api/sql/stream/{id}` SSE endpoint：建立 SSE 連線，推送 `fab_result` / `fab_error` / `complete` 事件
- [ ] 7.6 實作 per-Fab goroutine 並行執行：每個 Fab 一個 goroutine，結果寫入 channel，handler 讀取後即時 flush SSE
- [ ] 7.7 實作 per-Fab timeout：每個 goroutine 設定獨立 context timeout，超時推送 `fab_error` 事件
- [ ] 7.8 實作 Fab 清單驗證：請求中含無效 Fab 代號時回傳 400
- [ ] 7.9 撰寫後端單元測試：SELECT-only 檢查（正常 / 非 SELECT / WITH clause）、ROWNUM wrap 輸出、Test DB 超時攔截
- [ ] 7.10 撰寫後端整合測試：mock sidecar，驗證 SSE 事件依序推送、部分 Fab 失敗不影響其他 Fab

## 8. SQL Console 前端

- [ ] 8.1 定義 TypeScript interfaces：`SqlTemplate`、`SqlParam`、`FabResult`、`FabError`、`SseEvent`
- [ ] 8.2 實作 `FabQueryService`：封裝 `EventSource`，以 Signal 暴露 SSE 事件流（`fabResults`、`queryStatus`）
- [ ] 8.3 建立 `shared/fab-selector` 元件（多廠功能共用）：checkbox 群組，列出 14 個廠區，支援全選 / 全不選
- [ ] 8.4 建立 `shared/results/results.component.ts`（多廠功能共用）：根據 `viewMode` signal 切換 Flat Table / Diff / Pivot，含 `FabStatusChip` loading/done/error 狀態顯示
- [ ] 8.5 建立 `shared/results/flat-table.component.ts`：`fab` 欄固定最左，其餘欄位動態產生，各廠資料合併顯示
- [ ] 8.6 建立 `shared/results/diff-panel.component.ts`：`computed(() => detectDiff(fabResults()))` 高亮差異 cell，差異欄清單顯示於表格上方
- [ ] 8.7 建立 `shared/results/pivot-view.component.ts`：fab 橫排、欄位縱排的 Pivot 轉換與顯示
- [ ] 8.8 建立 SQL Console 頁面骨架（`sql-console/`）：左側控制區（Fab 選擇、ROWNUM、SQL 輸入、執行按鈕）+ 右側結果區，組合 shared 元件
- [ ] 8.9 實作情境 SQL 選單（`sql-console/context-sql/`）：呼叫 `GET /api/sql/templates`，下拉選擇後填入 Monaco Editor
- [ ] 8.10 實作 Monaco Editor 整合（`sql-console/sql-editor/`）：`@monaco-editor/angular` wrapper，OnPush
- [ ] 8.11 實作 named parameter 自動渲染（`NamedParamDirective`）：解析 `:param_name`，動態生成對應輸入欄位（含預設值）
- [ ] 8.12 實作 ROWNUM 輸入欄位：必填驗證、預設 100、最大值 300 的 Angular Reactive Form validator
- [ ] 8.13 實作執行前驗證：廠區至少一個、ROWNUM 合法、SQL 非空，驗證失敗顯示 inline 錯誤
- [ ] 8.14 實作 SSE 串流結果接收：訂閱 `fab_result` 事件，每筆到達即以 `fabResults.update()` 累加（加上 fab 欄）
- [ ] 8.15 實作失敗廠區 banner：接收 `fab_error` 事件，頁面頂部累積顯示失敗廠區與原因
- [ ] 8.16 設定 Angular routing：新增 `/sql-console` 路由
- [ ] 8.17 撰寫單元測試：named param 解析邏輯、`detectDiff()` 演算法、Pivot 資料轉換、`FabSelectorComponent` emit

## 9. 整合驗收測試

- [ ] 9.1 本地執行 `docker compose up`，確認三個容器正常啟動並互通
- [ ] 9.2 SQL Console：輸入合法 SELECT SQL，選擇 3 個 Fab，驗證結果以 SSE 串流累加顯示
- [ ] 9.3 SQL Console：輸入非 SELECT 語句（UPDATE），驗證前端顯示錯誤且不執行
- [ ] 9.4 SQL Console：ROWNUM 設定 50，驗證每個 Fab 結果筆數不超過 50
- [ ] 9.5 SQL Console：選擇情境 SQL，填入參數，驗證 named param 替換後正確執行
- [ ] 9.6 SQL Console：模擬一個 Fab sidecar 超時，驗證 banner 顯示該廠失敗，其他廠結果照常顯示
- [ ] 9.7 SQL Console：點擊 [Diff] 按鈕，驗證跨廠差異 cell 正確高亮
- [ ] 9.8 SQL Console：點擊 [Pivot] 按鈕，驗證表格切換為 fab 橫排格式
- [ ] 9.9 驗證 sidecar 完全斷線時前端顯示適當錯誤訊息
- [ ] 9.10 驗證無效 Fab 代號（如 F99）回傳 400 錯誤
