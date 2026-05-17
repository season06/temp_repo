# Core Workflows

## Data Access Pattern
所有 Oracle DB 存取皆透過 Sidecar Adapter（Python）：
```
Golang Backend → HTTP → Python Sidecar → Oracle SDK → Oracle DB
```
後端不直接連接 Oracle DB；所有 SQL 查詢委由 sidecar 執行。

## Feature Workflows

### 搜尋各廠 SOP
1. 使用者指定 `Fab` + 搜尋條件
2. 後端組合 SQL 查詢，呼叫 sidecar
3. Sidecar 執行 plain SQL，回傳結果
4. 後端整理資料，回傳給前端顯示

### 搜尋各廠 Cpnt
1. 使用者指定 `Fab` + 搜尋條件
2. 後端查詢對應廠區的 Cpnt 設定 table
3. 回傳 Cpnt 清單與設定詳情

### 搜尋執行失敗的 Cpnt 與對應 SOP
1. 查詢執行失敗記錄
2. 關聯對應的 SOP 與 Cpnt 設定
3. 回傳失敗清單供使用者排查
