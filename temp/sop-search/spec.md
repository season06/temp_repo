## ADDED Requirements

### Requirement: 依廠區篩選 SOP 清單
使用者 SHALL 能選擇一個廠區（Fab）並取得該廠區的 SOP 清單，清單包含 SOP ID、名稱、狀態等基本資訊。

#### Scenario: 選擇廠區後顯示 SOP 清單
- **WHEN** 使用者從廠區選擇器選擇一個有效的 Fab（如 `F12A`）
- **THEN** 系統 SHALL 顯示該廠區所有 SOP 的清單，每筆包含 SOP ID 與名稱

#### Scenario: 廠區無 SOP 資料
- **WHEN** 使用者選擇某廠區，但該廠區查無 SOP 資料
- **THEN** 系統 SHALL 顯示空清單並提示「此廠區目前無 SOP 資料」

### Requirement: 以關鍵字搜尋 SOP
使用者 SHALL 能在選定廠區後輸入關鍵字（SOP 名稱或 ID）進行模糊搜尋，系統 SHALL 回傳符合條件的 SOP 清單。

#### Scenario: 輸入名稱關鍵字搜尋
- **WHEN** 使用者在搜尋欄輸入部分 SOP 名稱並提交
- **THEN** 系統 SHALL 回傳所有名稱包含該關鍵字的 SOP（不區分大小寫）

#### Scenario: 輸入 SOP ID 搜尋
- **WHEN** 使用者輸入完整或部分 SOP ID
- **THEN** 系統 SHALL 回傳 ID 符合的 SOP 記錄

#### Scenario: 無符合搜尋結果
- **WHEN** 使用者輸入的關鍵字在該廠區無匹配的 SOP
- **THEN** 系統 SHALL 顯示「查無符合結果」提示

### Requirement: 查看 SOP 詳情
使用者 SHALL 能點選 SOP 清單中的單筆記錄，查看該 SOP 的完整設定詳情，包含其關聯的 Cpnt 清單。

#### Scenario: 點選 SOP 查看詳情
- **WHEN** 使用者點選清單中一筆 SOP
- **THEN** 系統 SHALL 顯示該 SOP 的詳細資訊，包含 SOP ID、名稱、描述、關聯 Cpnt 清單

#### Scenario: SOP 無關聯 Cpnt
- **WHEN** 使用者查看一筆沒有關聯 Cpnt 的 SOP 詳情
- **THEN** 系統 SHALL 顯示 SOP 基本資訊，並在 Cpnt 區塊顯示「此 SOP 無關聯積木」

### Requirement: SOP 清單分頁
當查詢結果筆數超過單頁上限時，系統 SHALL 提供分頁導覽，每頁最多顯示 20 筆。

#### Scenario: 結果超過一頁
- **WHEN** 查詢結果超過 20 筆
- **THEN** 系統 SHALL 顯示分頁控制項，使用者可切換頁次

#### Scenario: 切換分頁
- **WHEN** 使用者點選下一頁
- **THEN** 系統 SHALL 載入並顯示下一批 20 筆資料
