# Python 開發標準

> Code Review 目的: 保證專案的可讀性與一致性、提高程式碼可維護性、知識共享

https://www.explainthis.io/zh-hant/e-plus/blog/code-review

## Code Review 流程 & merge 標準
- JIRA 單狀態到 waitReview，經 code review 確認邏輯正確，才能開 PR
- Merge 到**版號 branch(主幹)** 必須發 PR，指定只少一位 reviewer
    - 至少一位 reviewer 按下 approved
    - 需通過 linter pipeline
    - 由 reviewer 對修改後的 comment 按 resolved

> Azure Setting (截圖)

## Python Coding Style
遵照 [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) 撰寫程式碼

- data model (pydantic)
    - 適用於有明確定義的 dict 或 json
    - 正面表列需要用到的 item

### Log
TBD

## Linter & Type Checking

### Pylint Ignore Rules
### Mypy Ignore Rules

## Git
- Commit Msg: convensional commit
    - https://wadehuanglearning.blogspot.com/2019/05/commit-commit-commit-why-what-commit.html
- Merge 到主幹前需整理 commit -> 符合"每個 commit 為一個完整且可執行的 feature"
- 善用 rebase 拉到最新進度

## Visual Studio Code Extension

## iSOP Kernal 開發原則
- 單一 function 單一職責，非必要一個 function 內容不得超過一個螢幕頁面
- if else 裡重複的邏輯需抽出來
- SQL 抽出 python 程式碼
- utility 共用 function 需按照功能分類
- 有明確資料格式的 dict variable，需定義 data_model，例如: sop_json
- 開 PR 單 merge 到主幹之前需整理 commit，一張工單在一個 PR 單裡面只能有一個 commit

### 資料夾結構
- config: 放置 env config yaml
- data_model: 定義資料內容
- data_handler: 對資料做基本處理 (sync, assign)
- service: 第三方服務
- sql:static sql
- utils

### 命名規範 Naming Convention
- `_client`: 連線第三方服務，例如: Mongo, Redis
- `_model`: 定義資料內容

### 縮寫規範


https://hackmd.io/mdHEXxO7TLOvjvgnD8H8_A