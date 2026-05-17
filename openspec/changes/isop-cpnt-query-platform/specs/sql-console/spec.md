## ADDED Requirements

### Requirement: 選擇查詢目標廠區
使用者 SHALL 能從 14 個有效廠區中多選查詢目標，至少選擇一個廠區才可執行查詢。

#### Scenario: 多選廠區後執行
- **WHEN** 使用者勾選多個 Fab 並執行查詢
- **THEN** 系統 SHALL 對每個選定的 Fab 並行執行相同 SQL

#### Scenario: 未選擇廠區即執行
- **WHEN** 使用者未勾選任何 Fab 即點擊執行
- **THEN** 系統 SHALL 顯示驗證錯誤「請至少選擇一個廠區」，不執行查詢

### Requirement: 設定 ROWNUM 上限
使用者 SHALL 能設定每個廠區最多回傳的資料筆數，此為必填欄位，預設值為 100，最大值為 300。

#### Scenario: 使用預設 ROWNUM
- **WHEN** 使用者未修改 ROWNUM 欄位即執行查詢
- **THEN** 系統 SHALL 對每個廠區限制回傳最多 100 筆資料

#### Scenario: 自訂 ROWNUM
- **WHEN** 使用者輸入 1–300 之間的整數
- **THEN** 系統 SHALL 以該數值作為每個廠區的資料筆數上限

#### Scenario: ROWNUM 超過上限
- **WHEN** 使用者輸入超過 300 的數值
- **THEN** 系統 SHALL 顯示驗證錯誤「最大筆數限制為 300」，不執行查詢

#### Scenario: ROWNUM 為空
- **WHEN** 使用者清空 ROWNUM 欄位即點擊執行
- **THEN** 系統 SHALL 顯示驗證錯誤「筆數為必填欄位」，不執行查詢

### Requirement: 自由輸入 SQL
使用者 SHALL 能在 SQL 輸入框中貼上或輸入任意 SQL 字串進行查詢。

#### Scenario: 輸入合法 SELECT SQL 並執行
- **WHEN** 使用者輸入合法的 SELECT 語句並點擊執行
- **THEN** 系統 SHALL 進行語法檢查與 Test DB 試跑後，對各廠區執行查詢

#### Scenario: 輸入非 SELECT 語句
- **WHEN** 使用者輸入 INSERT、UPDATE、DELETE、DROP 等非 SELECT 語句
- **THEN** 系統 SHALL 顯示錯誤「SQL Console 僅允許 SELECT 查詢」，不執行

#### Scenario: 輸入語法有誤的 SQL
- **WHEN** 使用者輸入語法錯誤的 SQL
- **THEN** 系統 SHALL 顯示語法錯誤訊息（來自 parser 或 Test DB 回傳），不執行

### Requirement: 選擇情境 SQL 範本
使用者 SHALL 能從預設的情境 SQL 選單中選擇範本，系統自動填入 SQL 輸入框，使用者可在執行前修改內容。

#### Scenario: 選擇無參數的情境 SQL
- **WHEN** 使用者從選單選擇一個純靜態的情境 SQL 範本
- **THEN** 系統 SHALL 將該 SQL 填入輸入框，不顯示額外參數輸入區

#### Scenario: 選擇含 Named Parameters 的情境 SQL
- **WHEN** 使用者選擇含有 `:param_name` 佔位符的情境 SQL 範本
- **THEN** 系統 SHALL 自動解析 SQL 中的參數名稱，並在輸入框下方渲染對應的參數輸入欄位（含預設值）

#### Scenario: 填寫參數後執行
- **WHEN** 使用者填寫情境 SQL 的參數值並執行
- **THEN** 系統 SHALL 以使用者填入的值取代 SQL 中的 named parameter 後執行查詢

### Requirement: Test DB 試跑驗證
執行前系統 SHALL 先對 Test DB 發送相同 SQL（含 ROWNUM 限制），確認在 timeout 秒數內有回應，通過後才對正式 Fab DB 執行。

#### Scenario: Test DB 試跑通過
- **WHEN** Test DB 在 timeout 內回傳結果
- **THEN** 系統 SHALL 繼續對選定的正式 Fab 執行查詢

#### Scenario: Test DB 試跑超時
- **WHEN** Test DB 查詢超過 timeout 秒數仍未回應
- **THEN** 系統 SHALL 顯示錯誤「查詢執行時間過長，請優化 SQL 後再試」，不對正式 DB 執行

### Requirement: 以 SSE 串流即時顯示各廠結果
後端 SHALL 對各廠區並行執行查詢，每當一個廠區完成即透過 SSE 推送結果至前端，前端 SHALL 即時累加顯示，不等待所有廠區完成。

#### Scenario: 第一個廠區完成
- **WHEN** 最快回應的廠區查詢完成
- **THEN** 前端 SHALL 立即顯示該廠區的資料列，其他廠區顯示載入中狀態

#### Scenario: 所有廠區陸續完成
- **WHEN** 各廠區查詢依序完成
- **THEN** 前端 SHALL 持續累加新廠區的資料列至結果表格

#### Scenario: 某廠區查詢失敗或超時
- **WHEN** 一個或多個廠區回傳錯誤或超過 timeout
- **THEN** 系統 SHALL 在頁面頂部顯示 banner 列出失敗廠區與原因，其餘廠區結果正常顯示

### Requirement: Flat Table 預設顯示
查詢結果 SHALL 預設以 Flat Table 格式顯示，最左欄為 `fab`，其後為 SQL 查詢的各欄位，所有廠區資料合併於同一張表。

#### Scenario: 結果正常顯示
- **WHEN** 有廠區資料回傳
- **THEN** 系統 SHALL 顯示含 `fab` 欄的合併表格，各廠資料依廠區代號分組排列

#### Scenario: 所有廠區皆無資料
- **WHEN** 所有選定廠區查詢結果均為空
- **THEN** 系統 SHALL 顯示「查無資料」提示

### Requirement: Diff 視覺化
使用者 SHALL 能點擊 [Diff] 按鈕，觸發跨廠差異比較，系統 SHALL 顯示 Diff Panel 並高亮有差異的 cell。

#### Scenario: 點擊 Diff 按鈕
- **WHEN** 結果已顯示，使用者點擊 [Diff] 按鈕
- **THEN** 系統 SHALL 對每個欄位計算所有廠區的值是否一致，不一致的 cell 以橘色高亮標示

#### Scenario: Diff Panel 顯示
- **WHEN** Diff 計算完成且存在差異
- **THEN** 系統 SHALL 在表格上方顯示 Diff Panel，列出有差異的欄位名稱

#### Scenario: 無跨廠差異
- **WHEN** Diff 計算完成且所有廠區所有欄位值完全一致
- **THEN** 系統 SHALL 顯示「所有選定廠區資料一致」提示，不顯示高亮

### Requirement: Pivot View
使用者 SHALL 能點擊 [Pivot] 按鈕，切換為以廠區為欄（橫排）、欄位為列（縱排）的 Pivot 視圖。

#### Scenario: 切換 Pivot View
- **WHEN** 使用者點擊 [Pivot] 按鈕
- **THEN** 系統 SHALL 將結果重新排列為 Pivot 格式：第一欄為欄位名稱，後續每欄對應一個 Fab

#### Scenario: 切換回 Flat Table
- **WHEN** 使用者在 Pivot View 中再次點擊切換按鈕
- **THEN** 系統 SHALL 回復為 Flat Table 顯示
