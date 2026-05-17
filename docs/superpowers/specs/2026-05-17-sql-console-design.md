# SQL Console 設計文件

**日期：** 2026-05-17  
**功能：** SQL Console — 跨廠區 Plain SQL 查詢介面  
**變更：** `openspec/changes/isop-cpnt-query-platform`

---

## 一、整體架構

三層架構，每層單一職責：

```
Angular (Browser)
  └─ SQLConsoleComponent
       ├─ MonacoEditor（SQL 輸入）
       ├─ FabSelectorComponent（多選，14 廠）
       ├─ ContextSQLSelectorComponent（YAML 範本）
       └─ ResultsComponent（Flat Table / Diff / Pivot）
            └─ FabQueryService（SSE client）

Golang Backend
  └─ POST /api/fabs/query  →  GET /api/fabs/stream/{id}（SSE）
       └─ /internal/fabquery/   ← 所有多廠查詢功能共用
            ├─ engine.go        goroutine fan-out + channel 收集
            ├─ testdb.go        Test DB 試跑
            ├─ validator.go     SELECT-only 強制
            └─ rownum.go        ROWNUM 自動包裹

Python Sidecar Adapter（每個 Fab + Test DB 各一）
  └─ HTTP endpoint 封裝 Oracle cx_Oracle SDK
       POST /query  →  { rows, columns }
```

**Request 生命週期：**

1. 使用者送出 SQL + 選擇的 Fab 清單
2. Backend 驗證（SELECT-only）→ Test DB 試跑 → 回傳 `queryId`
3. Frontend 以 `queryId` 開啟 SSE 連線
4. Backend 對每個 Fab 啟動 goroutine，結果逐一 flush 為 SSE event
5. Frontend 累積結果至 `signal<FabResult[]>()`，表格即時渲染

---

## 二、Frontend 元件

```
shared/                               ← 多廠功能共用元件
  fab-selector/
    fab-selector.component.ts         multi-select dropdown，emit signal<string[]>
  results/
    results.component.ts              根據 viewMode signal 切換顯示
    flat-table.component.ts           所有 fab rows 合一表，fab column 固定最左
    diff-panel.component.ts           computed(() => detectDiff(...))，高亮差異 cell
    pivot-view.component.ts           fabs 為欄，fields 為列
    fab-status-chip.component.ts      loading / done / error 狀態

sql-console/                          ← SQL Console 專屬
  sql-console.component.ts            頁面容器，持有所有 signals
  sql-console.component.html

  context-sql/
    context-sql.component.ts          情境 SQL 選擇器，選後填入 editor
    context-sql.service.ts            GET /api/console/templates → 快取

  sql-editor/
    sql-editor.component.ts           Monaco wrapper（@monaco-editor/angular），OnPush
    named-param.directive.ts          偵測 :param 語法，動態 render 輸入框
```

**State model（全在 SQLConsoleComponent）：**

```ts
selectedFabs = signal<string[]>([])
sql          = signal<string>('')
rowLimit     = signal<number>(100)
queryId      = signal<string | null>(null)
fabResults   = signal<FabResult[]>([])
viewMode     = signal<'flat' | 'diff' | 'pivot'>('flat')

diffColumns  = computed(() => detectDiff(this.fabResults()))
```

`FabQueryService` 封裝 `EventSource`；每個 SSE event → `fabResults.update()`，Angular 透過 Signals 自動 reactive。子元件透過 `input()` + `output()` 溝通，不使用 NgRx。

---

## 三、Backend 資料流

### 執行流程

```
POST /api/fabs/query
  body: { sql, fabs, rowLimit, namedParams }
  │
  ├─ validator.go：解析 SQL AST，確認為 SELECT
  │    └─ 失敗 → 400 { error: "only SELECT allowed" }
  │
  ├─ rownum.go：包裹為 SELECT * FROM (...) WHERE ROWNUM <= :limit
  │
  ├─ testdb.go：送 Test DB sidecar 試跑（timeout: 5s）
  │    └─ 超時或語法錯誤 → 400 { error: "..." }
  │
  ├─ 建立 queryId（UUID），存入 in-memory map（TTL 5min）
  └─ 200 { queryId }

GET /api/fabs/stream/{queryId}
  │
  ├─ 設定 SSE headers（Content-Type: text/event-stream, Cache-Control: no-cache）
  ├─ engine.go：對每個選定 Fab 啟動 goroutine
  │    └─ goroutine：POST sidecar /query → 結果送入 channel（逾時 30s）
  │
  ├─ SSE flush loop：
  │    for result := range resultChan {
  │      write: { fab, rows, columns, status }
  │      flush()
  │    }
  └─ 全部完成 → 送 { type: "done" } → 關閉連線
```

### Sidecar 通訊

每個 Fab 對應一個 sidecar endpoint，URL 從 config 讀取。Goroutine 逾時 30s per fab；失敗的 fab 送出 `{ fab, status: "error", message }` event，不阻斷其他 fab。

### 關鍵參數

| 參數 | 預設值 | 上限 |
|------|--------|------|
| rowLimit | 100 | 300 |
| Test DB timeout | 5s | — |
| Per-fab goroutine timeout | 30s | — |
| queryId TTL | 5min | — |

---

## 四、錯誤處理

**原則：快速失敗在前（POST 階段），部分失敗在後（SSE 階段）。**

| 情境 | 層級 | 行為 |
|------|------|------|
| 非 SELECT 語法 | Backend POST | 400，立即回傳，不進入 Test DB |
| Test DB 超時（>5s） | Backend POST | 400，說明 query 過慢 |
| Test DB 語法錯誤 | Backend POST | 400，回傳 Oracle 錯誤訊息 |
| Named param 未填 | Frontend | 送出前 disable 按鈕，提示必填 |
| rowLimit 超出 300 | Frontend + Backend | Frontend 截斷；Backend 二次驗證 |
| 單一 Fab sidecar 失敗 | Backend SSE event | `{ fab, status:"error" }` → 繼續其他 fab |
| 所有 Fab 失敗 | Frontend | 顯示全域錯誤 banner |
| SSE 連線中斷 | Frontend | `EventSource.onerror` → 顯示重試提示 |
| QueryId 不存在/過期 | Backend SSE | 404 → frontend 顯示「查詢已過期，請重新執行」 |

**Partial failure UX：**  
每個 fab 有獨立 `FabStatusChip`（loading → done / error）。失敗的 fab 在表格顯示 error row，不影響其他 fab 結果。使用者可看到「12/14 廠區成功」。

---

## 五、測試策略

### Backend（Go）

| 類型 | 涵蓋目標 | 工具 |
|------|----------|------|
| Unit | `validator.go`：SELECT / 非 SELECT 各語法 | `go test` |
| Unit | `rownum.go`：包裹輸出正確性 | `go test` |
| Unit | `engine.go`：goroutine fan-out、channel 收集、部分失敗 | `go test` + mock sidecar |
| Unit | `testdb.go`：超時邏輯 | `go test` + fake HTTP server |
| Integration | POST → SSE 完整流程，mock sidecar 回傳固定資料 | `httptest` |
| Integration | SSE event 順序與 `done` 事件 | `httptest` |

### Frontend（Angular）

| 類型 | 涵蓋目標 | 工具 |
|------|----------|------|
| Unit | `detectDiff()`：同值/異值/缺 fab | Jasmine |
| Unit | `FabQueryService`：SSE event 解析、`fabResults` 累積 | Jasmine + EventSource mock |
| Unit | `NamedParamDirective`：`:param` 偵測與輸入框渲染 | Angular Testing |
| Component | `FabSelectorComponent`：全選/取消、emit 正確 | Angular Testing |
| Component | `ResultsComponent`：flat/diff/pivot 切換 | Angular Testing |

### Acceptance（E2E）

使用真實 Test DB sidecar，驗證：

- SELECT 允許執行
- 非 SELECT（INSERT/UPDATE/DROP）被拒絕並回傳 400
- 部分 fab 失敗時，其他 fab 仍正常回傳結果
- rowLimit 300 上限被強制執行
- Named param 替換後 SQL 正確傳遞

---

## 六、設計決策摘要

| 決策 | 選擇 | 理由 |
|------|------|------|
| SQL 編輯器 | Monaco Editor（`@monaco-editor/angular`） | 語法高亮、鍵盤快捷鍵、與現有設計整合 |
| 前端狀態管理 | Angular 21 Signals（無 NgRx） | 功能規模不需要 NgRx，Signals 足夠 |
| 串流機制 | SSE（Server-Sent Events） | 單向推送、HTTP 原生支援、不需 WebSocket |
| 多廠共用架構 | `/internal/fabquery` 共用 package | SOP/Cpnt 搜尋未來也需要相同機制 |
| SELECT 強制 | SQL AST parser（後端） | 防止誤用，前端不可信 |
| ROWNUM 包裹 | 後端自動包裹 | 使用者不需關心分頁語法 |
| Test DB 驗證 | 試跑後才存取正式 DB | 避免慢查詢打垮各廠 DB |
| Diff 計算 | 前端 Signal computed（`Set` 演算法） | 不需後端支援，即時反應 |
| 情境 SQL 設定 | YAML config file | 簡單、版控友好，預留 admin 擴充彈性 |
