# ISOP-Component-Platform

## Product Context & Objectives
WHAT: 一鍵查詢各廠的 API 設定與 API 執行結果，並顯示給使用者
WHO: team members (<20)

## Tech Stack
- 前端: Angular
- 後端: Golang
- infra: (local) docker, (prod) Kubernetes
- 第三方資料庫: Oracle DB 
    (Note: 並非自行架設，而是公司內部已有的基礎建設，該專案僅存取特定 table 的資料)

## Domain Terms & Relationship
- 積木 Component (`Cpnt`): 代指 iSOP 系統中第三方 API 的設定
- `SOP`: 運行於 iSOP 系統上，具有標準化流程的 workflow，一隻 `SOP` 可呼叫多個 `Cpnt`
- 廠區 (`Fab`): iSOP 系統架設於多個廠區環境中，每個 `Fab` 都有各自的 `Cpnt` 設定
    fabs = ['F12A', 'F12B', 'F14A', 'F14B', 'F15A', F15B', 'F16', 'F18A', 'F18B', 'F21', 'F22', 'F23', 'APOD', 'SOIC']

## Core Workflows
以 plain sql 的方式存取 Oracle DB 獲得 SOP, Cpnt 數據

### Features
根據 DB schema 查找資料 (like 電商商品列)
- 搜尋各廠 SOP
- 搜尋各廠 Cpnt
- 搜尋執行失敗的 Cpnt 與對應的 SOP

## External Dependencies
- 將存取 Oracle DB 的第三方 sdk (由 python 撰寫) 以 Sidecar Adapter 的模式運行，並開出端口讓主程式串接