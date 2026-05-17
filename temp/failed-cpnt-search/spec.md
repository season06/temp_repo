## ADDED Requirements

### Requirement: 查詢執行失敗的 Cpnt 清單
使用者 SHALL 能選擇一個廠區查詢該廠區中執行失敗的 Cpnt 記錄，清單包含 Cpnt 名稱、失敗時間、失敗原因摘要。

#### Scenario: 查詢指定廠區的失敗 Cpnt
- **WHEN** 使用者選擇廠區並進入失敗 Cpnt 查詢頁面
- **THEN** 系統 SHALL 顯示該廠區所有執行失敗的 Cpnt 記錄，依失敗時間降序排列

#### Scenario: 廠區無失敗記錄
- **WHEN** 使用者查詢某廠區但無失敗 Cpnt 記錄
- **THEN** 系統 SHALL 顯示「此廠區目前無執行失敗記錄」

### Requirement: 查看失敗 Cpnt 的關聯 SOP
使用者 SHALL 能在失敗 Cpnt 清單中看到每筆失敗記錄所屬的 SOP，以利追蹤影響範圍。

#### Scenario: 顯示關聯 SOP 資訊
- **WHEN** 系統顯示失敗 Cpnt 清單
- **THEN** 每筆記錄 SHALL 顯示觸發該 Cpnt 的 SOP ID 與名稱

#### Scenario: 點選 SOP 連結
- **WHEN** 使用者點選失敗記錄中的 SOP 名稱
- **THEN** 系統 SHALL 導向該 SOP 的詳情頁面

### Requirement: 依時間範圍篩選失敗記錄
使用者 SHALL 能指定時間區間（起始日期與結束日期）來篩選失敗 Cpnt 記錄，預設顯示最近 7 天。

#### Scenario: 使用預設時間範圍
- **WHEN** 使用者進入失敗 Cpnt 查詢頁面未指定時間範圍
- **THEN** 系統 SHALL 預設查詢最近 7 天的失敗記錄

#### Scenario: 自訂時間範圍
- **WHEN** 使用者輸入自訂的起始與結束日期並查詢
- **THEN** 系統 SHALL 回傳該時間區間內的失敗記錄

#### Scenario: 時間範圍無效
- **WHEN** 使用者輸入結束日期早於起始日期
- **THEN** 系統 SHALL 顯示驗證錯誤「結束日期不得早於起始日期」，不執行查詢

### Requirement: 失敗 Cpnt 清單分頁
當查詢結果筆數超過單頁上限時，系統 SHALL 提供分頁導覽，每頁最多顯示 20 筆。

#### Scenario: 結果超過一頁
- **WHEN** 失敗記錄超過 20 筆
- **THEN** 系統 SHALL 顯示分頁控制項供使用者切換頁次
