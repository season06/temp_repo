# Agent Template

一個讓開發者快速建立 agent 的 library。

使用對象: 90% 的人沒有程式基礎但需要開發 agent、10% 有更進階的技術需求調教 agent
原則: 高彈性與擴充性、讓使用者開發體驗良好

- 使用底線:「4 行樣板 + 改 config」。所有行為都能從 config 控制，樣板永遠不用改。不做 CLI。
- 主力 DX 場景: 使用者寫 skill 與簡單 tool。
- 舊 `agent-template` 分支僅作參考，本專案從零實作。

## Tech Stack

- uv、src layout
- Python >= 3.11
- deepagents >= 0.6, < 0.7
- langchain tool
- 套件名: `agent_template`，發佈為內部 wheel / git dependency

## Quick Start for user

```python
from agent_template import AgentBuilder

agent = AgentBuilder("config.yaml").build()
answer = agent.invoke("what time is it")
print(answer)
```

## Components

### Agent Builder

- 可支援不同 agent provider (deepagent, claude sdk)，**目前僅實作 deepagent**
- `AgentBuilder` 為 dispatch mode，根據 `agent.provider` 決定分發的 agent object
- `AgentBuilder(config)` 只收 config 檔路徑 (str/Path):
    - 自動載入 config 檔同目錄的 `.env`（不覆蓋既有環境變數）
    - config 內相對路徑以 config 檔所在目錄為基準解析（非 cwd）
    - config 驗證 fail fast: 未知欄位（打錯字）直接報錯，錯誤訊息人話化
- init 階段 merge local mcp / tool / skill
- `build()` 支援原生 agent kwargs 透傳，以 deepagent 為例:
    ```python
    agent = AgentBuilder("config.yaml").build(
        memory=...,
        subagents=...,
    )
    # 內部最終呼叫 create_deep_agent(**kwargs)
    ```

### Model

- 只支援 OpenAI-compatible API: `config.agent.model` 填模型名，搭配環境變數 `LLM_API_KEY` / `LLM_BASE_URL`
- 逃生口: `build(model=<LangChain model 物件>)` 供進階使用者自建 model

### Middleware

- SDK 有一組**必要 middleware**（具體項目待定），建 agent 時一律掛上
- 使用者可經 `build(middleware=[...])` 傳自訂 middleware（middleware 是程式物件，不走 config）
- 合併順序:SDK 內建在前、使用者在後；必要 middleware 不可被移除

### 衝突規則

一句話: **衝突時 config 贏，且一定發 warning 告知**。

- 純量型（model、system_prompt）: config 與 build() 同時提供 → 取 config、發 warning
- 集合型（tools、skills、mcp）: config 與 build() 兩邊 merge
- merge 撞名（同名 tool / skill）: 留 config 那份、丟棄 build() 那份、發 warning

### Load local mcp / tool / skill

- mcp（來源: config）
    - 只支援 `streamable-http` transport（config 保留 `transport` 欄位以利未來擴充）
    - 連線失敗 → warning + 跳過該 server，不擋 build
- tool（來源: config 指定目錄、`build()` 傳入）
    - 遞迴掃描目錄，只收 module 層級的 `BaseTool` 實例（即 `@tool` 裝飾過的函式），未裝飾的函式一律忽略
    - 跳過 `_` 開頭的檔案；單一檔案 import 失敗 → warning + 跳過，不擋 build
- skill（來源: config 指定目錄、`build()` 傳入）
    - config entry 為 **skills 根目錄**: SDK 掃描其下每個含 `SKILL.md` 的子目錄，各算一個 skill
    - 缺 `SKILL.md` 的子目錄 → warning + 跳過
    - 使用 deepagent 原生 skill 機制（`skills=` 傳來源路徑），不轉成 tool

### 執行介面

- `build()` 回傳薄包裝 `Agent`，非原生物件:
    - `invoke(str) -> str`: 字串進、字串出（90% 路徑）；傳 dict 則透傳原生行為、回傳原生 state
    - `stream(str)`: 最簡版，只逐段吐 AI 訊息文字，tool call 過程靜默；dict 同樣透傳
    - `ainvoke` / `astream`: 上述兩者的 async 鏡像
    - `agent.native`: 底層原生 agent，LangGraph 全能力（checkpoint、原生 stream mode 等）由此取用
- async 約束:
    - MCP tool 是 async-only，同步糖衣內部須走 async 路徑（`asyncio.run(native.ainvoke(...))`）
    - init 階段載 MCP 使用 loop-aware runner: 無 event loop 用 `asyncio.run`；已在 loop 內則另開 thread 跑新 loop

### Observability

警告雙軌制:

- **設定問題**（衝突、撞名、載入失敗、MCP 連不上、config 錯誤）→ `warnings.warn()`，預設可見
- **運作紀錄**（載入了幾個 tool 等）→ `logging.getLogger("agent_template")` + `NullHandler`，遵守 SDK logger 不影響開發者程式的規則

## 範例

`example/` 即使用者起手式範本，複製整個資料夾就能開工:

- `config.yaml`
- `tools/`: 一個最小 `@tool` 範例
- `skills/`: 一個含 `SKILL.md` 的範例 skill
- `agent.py`: 示範 `invoke` + `stream`
- MCP 在 config 中以註解範例呈現（需要活的 server 才能跑）

## 測試

最小單元測試，不碰真 LLM、不需網路:

- config 驗證（未知欄位報錯）
- 衝突規則（config 贏 + warning、撞名處理）
- tool 目錄掃描、skill 根目錄掃描、路徑解析

端到端驗證靠手動執行 `example/agent.py`。

## 第二階段（本期不做）

- a2a
- MCP stdio / sse transport
- stream 進度版（tool call 提示、subagent 訊息透出）
- CLI 入口
- claude sdk provider
