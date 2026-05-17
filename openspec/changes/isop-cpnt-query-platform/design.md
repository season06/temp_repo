## Context

ISOP-Component-Platform 是一個全新專案，無既有程式碼。目標是讓 team members（< 20 人）能透過單一 Web UI 跨 14 個廠區查詢 iSOP 系統的 SOP 設定、Cpnt 設定，以及執行失敗的 Cpnt 記錄。

核心限制：Oracle DB 為公司共用基礎建設，只能唯讀存取特定 table，且必須透過公司提供的 Python SDK 存取，不可使用一般資料庫 driver 直連。

## Goals / Non-Goals

**Goals:**
- 建立三層架構：Angular 前端 → Golang API 後端 → Python Sidecar → Oracle DB
- 支援跨廠（14 個 Fab）的 SOP、Cpnt 搜尋與失敗記錄查詢
- 可在本地 Docker Compose 一鍵啟動；生產環境部署至 Kubernetes

**Non-Goals:**
- 不寫入 Oracle DB（純查詢）
- 不實作使用者驗證/權限控管（team 內部工具，信任網路隔離）
- 不實作即時通知或 webhook
- 不管理或修改 Cpnt / SOP 設定

## Decisions

### 決策一：Sidecar Adapter 架構
**選擇**：Python sidecar 作為獨立 HTTP 服務，後端以 HTTP 呼叫。

**理由**：公司 Oracle SDK 為 Python 套件，Golang 無法直接使用；透過 sidecar 橋接可讓後端語言選擇自由，且 sidecar 介面穩定後可被其他服務複用。

**替代方案考量**：
- CGO 呼叫 C 函式庫 → Oracle SDK 無 C bindings，不可行
- gRPC → 增加 protobuf 維護成本，HTTP 已足夠

### 決策二：plain SQL，不使用 ORM
**選擇**：所有 Oracle 查詢以 raw SQL string 撰寫。

**理由**：Oracle DB 結構已固定（非自管），schema 不會變動；ORM 的 migration 管理對只讀場景是過度設計；SQL 更易 debug 和審核。

### 決策三：前端使用 Angular Standalone Components
**選擇**：採用 Angular standalone component 模式（NgModule-free）。

**理由**：減少樣板程式碼；lazy loading 更直覺；符合 Angular 17+ 推薦做法。

### 決策四：Fab 選擇器為全域共用元件
**選擇**：廠區選擇放在 shared module，跨三個查詢頁面共用。

**理由**：三個功能都需要指定廠區，統一元件確保行為一致，避免重複實作。

### 決策五：後端不做資料快取
**選擇**：每次查詢直接打 sidecar，不加 in-memory cache。

**理由**：team 規模小（< 20 人），Oracle 查詢頻率低，快取增加的狀態管理複雜度不值得；如未來有需要可加 Redis 層。

### 決策六：SQL Console 串流採用 SSE（Server-Sent Events）
**選擇**：後端用 Go goroutine 並行打各 Fab，結果透過 SSE 推送至前端。

**流程**：
```
POST /api/sql/execute  → 取得 execution_id
GET  /api/sql/stream/{id}  → SSE 連線

後端：goroutine per Fab → channel → SSE flush
前端：EventSource → 累加顯示，不等全部完成
```

**理由**：SSE 為單向推送，實作比 WebSocket 簡單；Angular 可用 `EventSource` 包 RxJS Observable，無需額外套件；不需要雙向通訊。

**替代方案考量**：
- WebSocket → 雙向，此場景用不到
- Polling → 有延遲感，且前端需管理 interval

### 決策七：ROWNUM 由後端自動 wrap
**選擇**：後端在送 sidecar 前，自動將使用者 SQL 包裹 ROWNUM 限制。

```sql
-- 使用者輸入：
SELECT name, api_url FROM cpnt WHERE status = 'ACTIVE'

-- 後端送 sidecar：
SELECT * FROM (
  SELECT name, api_url FROM cpnt WHERE status = 'ACTIVE'
) WHERE ROWNUM <= :row_limit
```

**理由**：使用者不應自行管理 ROWNUM，統一由後端注入確保每個 Fab 都受到保護；sidecar 保持無狀態、不感知 row limit 邏輯。

**限制**：若使用者 SQL 已含 ORDER BY，subquery wrap 是 Oracle 的標準正確做法，不影響排序語意。

### 決策八：SELECT-only 強制在後端語法層做
**選擇**：後端以 SQL parser library 解析 top-level statement type，非 SELECT 一律拒絕，不到達 sidecar。

**理由**：sidecar 只是執行橋接層，安全邊界應在後端；parser 比 regex 可靠，可正確處理 WITH clause（CTE）等合法 SELECT 變體。

**接受的風險**：SELECT 語句仍可能觸發 Oracle function side effects，但此為 internal tool 且使用者為 team members，接受此風險。

### 決策九：情境 SQL 以 YAML config 管理，保留 admin 擴充彈性
**選擇**：情境 SQL 定義於 `config/context_sqls.yaml`，支援靜態 SQL 與 named parameters 兩種形式。

```yaml
sqls:
  - id: failed-cpnt-recent
    name: 查詢最近失敗的 Cpnt
    sql: |
      SELECT c.name, e.error_msg, e.fail_time
      FROM cpnt c JOIN cpnt_execution_log e ON c.id = e.cpnt_id
      WHERE e.status = 'FAILED' AND e.fail_time > SYSDATE - :days
    params:
      - name: days
        label: 天數
        type: integer
        default: 7
```

**理由**：config file 易於版本控管；`params` 欄位讓前端可自動渲染參數輸入框；未來若需要 admin UI 新增範本，只需將 config 搬至 DB table，介面層不需改變。

### 決策十：跨廠 Diff 演算法於前端計算
**選擇**：Diff 計算在前端進行（對每欄位做 SET 去重），不呼叫額外後端 API。

**算法**：對每個 column，收集所有 fab 的值組成 Set；若 `Set.size > 1` 則該欄有差異，高亮顯示。

**理由**：資料已在前端（SSE 接收完畢），前端計算即時且無網路成本；邏輯簡單，不需後端介入。

## Risks / Trade-offs

- **Sidecar 單點故障** → Sidecar crash 導致所有查詢失敗。緩解：後端加 health check endpoint；Kubernetes 設定 liveness probe 自動重啟。
- **Oracle DB 連線逾時** → 公司網路問題或 DB 負載高時查詢慢。緩解：Sidecar client 設定 10s timeout，回傳明確錯誤訊息。
- **SQL injection** → 搜尋條件直接拼接 SQL 有風險。緩解：所有查詢使用 Oracle named parameters（`:param`），不做字串拼接。
- **Fab 代號異動** → 廠區清單硬編碼，新增廠區需改程式碼。緩解：Fab list 集中定義為 config，不散落各處。

## Migration Plan

1. 本地開發：`docker compose up` 啟動三個 container（frontend、backend、sidecar）
2. 生產部署：建立 Kubernetes Deployment（backend + sidecar 同 Pod）+ Service + Ingress
3. 不需資料 migration（唯讀，無自管 DB）
4. Rollback：更新 Kubernetes image tag 即可回滾

## Open Questions

- Oracle table 名稱與欄位定義需向 iSOP 系統管理員確認（待取得 schema 文件）
- Sidecar 與後端的 internal port 號需與 infra team 對齊（暫定 8080）
- 前端是否需要支援多廠區同時查詢（目前設計為單廠區）
