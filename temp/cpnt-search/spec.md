## ADDED Requirements

### Requirement: 依廠區篩選 Cpnt 清單
使用者 SHALL 能選擇一個廠區（Fab）並取得該廠區的 Cpnt（積木）清單，清單包含 Cpnt ID、名稱、API 端點等基本設定資訊。

#### Scenario: 選擇廠區後顯示 Cpnt 清單
- **WHEN** 使用者從廠區選擇器選擇一個有效的 Fab
- **THEN** 系統 SHALL 顯示該廠區所有 Cpnt 的清單，每筆包含 Cpnt ID 與名稱

#### Scenario: 廠區無 Cpnt 資料
- **WHEN** 使用者選擇某廠區，但該廠區查無 Cpnt 設定
- **THEN** 系統 SHALL 顯示空清單並提示「此廠區目前無積木設定」

### Requirement: 以關鍵字搜尋 Cpnt
使用者 SHALL 能在選定廠區後輸入 Cpnt 名稱關鍵字進行搜尋，系統 SHALL 回傳名稱包含關鍵字的 Cpnt 清單。

#### Scenario: 輸入關鍵字搜尋 Cpnt
- **WHEN** 使用者輸入部分 Cpnt 名稱並提交搜尋
- **THEN** 系統 SHALL 回傳該廠區中名稱包含關鍵字的所有 Cpnt（不區分大小寫）

#### Scenario: 無符合搜尋結果
- **WHEN** 搜尋關鍵字在該廠區無匹配的 Cpnt
- **THEN** 系統 SHALL 顯示「查無符合結果」提示

### Requirement: 查看 Cpnt 設定詳情
使用者 SHALL 能點選 Cpnt 清單中的單筆記錄，查看該積木的完整 API 設定，包含端點 URL、參數定義、認證方式等。

#### Scenario: 點選 Cpnt 查看詳情
- **WHEN** 使用者點選清單中一筆 Cpnt
- **THEN** 系統 SHALL 顯示該 Cpnt 的完整設定詳情

#### Scenario: 顯示關聯的 SOP 清單
- **WHEN** 使用者查看一筆 Cpnt 的詳情
- **THEN** 系統 SHALL 列出所有引用此 Cpnt 的 SOP 名稱

### Requirement: Cpnt 清單分頁
當查詢結果筆數超過單頁上限時，系統 SHALL 提供分頁導覽，每頁最多顯示 20 筆。

#### Scenario: 結果超過一頁
- **WHEN** 查詢結果超過 20 筆
- **THEN** 系統 SHALL 顯示分頁控制項供使用者切換頁次

#### Scenario: 切換分頁
- **WHEN** 使用者點選下一頁
- **THEN** 系統 SHALL 載入並顯示下一批 20 筆 Cpnt 資料
