# Domain Terms

## Spec 語言
所有 spec、requirement、設計文件一律以 **zh-tw（繁體中文）** 撰寫。

## Core Entities

### 積木 Component (`Cpnt`)
iSOP 系統中第三方 API 的設定單元。
每個 `Cpnt` 代表一個可被 SOP 呼叫的外部 API 設定。

### SOP
運行於 iSOP 系統上具有標準化流程的 workflow。
一隻 SOP 可呼叫多個 `Cpnt`。

### 廠區 (`Fab`)
iSOP 系統架設的生產環境節點。
每個 `Fab` 有各自獨立的 `Cpnt` 設定。

有效廠區清單：
```
F12A, F12B, F14A, F14B, F15A, F15B, F16, F18A, F18B, F21, F22, F23, APOD, SOIC
```

## Relationships
- 一個 `SOP` 包含多個 `Cpnt` 的呼叫步驟
- 每個 `Fab` 各自維護一套 `Cpnt` 設定
- 查詢時需指定 `Fab` 才能取得對應的 `Cpnt` 和 `SOP` 資料
- 提及「全廠區」則代表 Fab 有效廠區清單，不列舉（共 14 個）

## Abbreviations
| 縮寫 | 全稱 |
|------|------|
| `Cpnt` | Component（積木） |
| `Fab` | 廠區 (Fabrication site) |
| `SOP` | Standard Operating Procedure |
| `iSOP` | 公司內部 SOP 管理系統 |
