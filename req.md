# Agent-Template 最小可行性產品 (MVP) 需求規格書

## 專案定位
- 定位：輕量、高擴充性、支援多框架 (Framework-agnostic) 的 AI Agent 開發套件 (SDK)。
- 核心目標：讓開發者能以統一的介面，快速構建、組合並部署 AI Agent。
- MVP 階段重點：優先支援 DeepAgent，並預留未來接入 Claude、Harness 等其他 Agent 的抽象層。
- LLM 接口：僅支援 **OpenAI-compatible** 端點（`base_url` + `api_key` + `model`）。團隊模型皆為地端模型，透過相容端點存取。

## 架構模型（核心設計原則）
本 SDK 的「framework-agnostic」定義在**建構期**，而非執行期：

- **統一建構**：所有框架都必須實作最小共同介面 —— `build_agent` / `add_skill` / `add_mcp`。`build_agent` 回傳**原生 agent object 本身**。
- **注入式儀器化**：Hook / Middleware、Auth、Observability 等橫切關注點，在**建構期就注入**原生物件（對 DeepAgent = 建構時掛載 middleware）。回傳的雖是原生物件，但已被儀器化。未來每個框架的 adapter 各自負責，把 SDK 的 hook / auth / o11y 翻譯成該框架的擴充機制。
- **執行期回歸原生**：`invoke` / `stream` 等執行期方法**不被 SDK 統一**，使用者拿到什麼框架就用該框架的原生呼叫方式。

> 註：先前的「`SecureAgent` allow-list 包裝層（封鎖 streaming / with_config）」**不在本 MVP scope**（會攔截原生物件且與 streaming 需求衝突）。本 MVP 的安全性僅保留 Feature 5 的 auth hook。

## Core Architecture
SDK 將採用模組化設計，主要分為以下幾個核心模組：

- Agent Core：負責管理 Agent 的生命週期、狀態與 LLM 互動
- Plugin System：提供 Skill 與 MCP (Model Context Protocol) 的接入標準
- Middleware/Hook Pipeline (中間件機制)：負責請求/響應的攔截、Auth 驗證與日誌記錄
- A2A Router：負責多 Agent 之間的協作與通訊
- Observability：基於 OpenTelemetry 的追蹤與監控
- Config：將 llm-key、model、otel endpoint 等資訊 config 化

## Features

### 1. BaseAgent
需求描述：提供統一的 Agent 抽象類別（建構期統一介面）。
- 實做細節
  - 現階段先實做 DeepAgent 驅動，LLM 統一走 OpenAI-compatible 端點。
  - 定義 AgentConfig（包含 API Key、Model Name、Temperature、System Prompt 等）。
  - `build_agent` 回傳**原生 agent object**（已於建構期注入 hook / auth / o11y）。
  - 使用者可直接對回傳的原生物件呼叫 `invoke` / `stream`（執行期回歸各框架原生 API）。

### 2. Agent-to-Agent 協定
需求描述：支援多個 Agent 之間互相呼叫、協作與訊息傳遞；同一 agent 同時具備 client（呼叫別人）與 server（被呼叫）角色。
- 實做細節
  - 採用**標準 A2A 協定**。
  - agent_server：實現 `invoke`、`stream`，一鍵啟動 A2A server。
  - agent_client：存取其他 agent。
  - **定址 / 服務發現**：走 A2A 標準的 Agent Card（`/.well-known/agent.json`）—— client 先抓取目標 agent 的 card，再據以呼叫。
  - **入站認證**：A2A 入站請求**共用 Feature 5 的 auth hook**（被其他 agent 呼叫時，一樣經 auth 端點驗證）。
  - 接收 A2A 請求後驗證 message 結構、streaming chunk 推送。

### 3. Hook / Middleware 機制 (攔截器)
需求描述：允許開發者在 Agent 運行的各個生命週期節點插入自定義邏輯。
- 實做細節
  - 在呼叫 llm / skill / mcp 之前，進行驗證項目（auth 驗證節點）。
  - 在呼叫 llm / skill / mcp 之後，若遇到狀態為 `session_stop`（由 agent server 或 mcp server 依團隊標準化狀態回覆）則優雅中止該輪執行。
  - **「一輪 / session」定義**：指**一次 agent 執行** —— 從使用者或 A2A 呼叫進入，到本次產出結束為止；期間所有內部 llm / skill / mcp / a2a 呼叫皆屬同一輪。任何 server 回 `session_stop`，即優雅中止這整次執行並回傳當下結果。
    - （對話級 / 跨多次呼叫的停止，需搭配 checkpointer 的狀態持久化，本 MVP 不做，留待後續。）

### 4. Skill 與 MCP 整合方法 (add_skill, add_mcp)
需求描述：讓 Agent Template SDK 具備擴充能力，可支援不同 agent 增加 mcp、skill 的方式。
- 實做細節
  - 實做 mcp client（須處理 mcp 連線、生命週期、tool 轉換）。
    - **Transport**：同時支援 **stdio**（本地子行程）與 **HTTP / SSE**（遠端 server）。
    - **多重掛載**：`add_mcp` 可重複呼叫，累加多個 MCP server。
  - 實做 skill client：從 skill-registry 取得 skill content。
    - skill-registry 規格團隊**討論中，MVP 先 mock**。
    - **多重掛載**：`add_skill` 可重複呼叫，累加多個 skill。

### 5. 權限驗證 (Authentication & Authorization)
需求描述：確保 Agent 在存取 MCP / Skills 或與其他 Agent 通訊時，必須經過身份與權限驗證。
- 實做細節
  - 利用 Hook / Middleware 機制：在 before 階段，攔截即將執行的 Tool 請求。
  - **同一條 auth hook 亦套用於 A2A 入站請求**（見 Feature 2）。
  - MVP 需求：發送一個 http request 到 auth 端點，確認回應狀態，200 代表認證通過。
  - auth 端點的完整契約（帶什麼身份 / token、授權粒度）團隊**討論中，MVP 先用 HTTP mock**。

### 6. Observability
需求描述：提供生產環境等級的監控，讓開發者能追蹤 Agent 的決策鏈、Token 消耗與 Tool 執行時間。三種訊號皆走 **OpenTelemetry SDK** 蒐集。
- Resource 屬性（每個訊號一律附帶）：專案 `cid`、`agent_version`、`service.name`、`framework`、`model`。
- **Trace**
  - 使用 OpenTelemetry SDK 蒐集，經 OTLP 匯出至 **otel-collector**；**Langfuse (SaaS)** 消費 OTLP 呈現完整 Trace Tree。
  - 以「一次 agent run」為 root span，子 span 涵蓋 `llm_call` / `skill_call` / `mcp_call` / `a2a_call`。
- **Metrics**
  - `tool_calls_total{tool,status}`：call_tool 次數 / 失敗率。
  - `tool_call_duration{tool}`（histogram）：Tool 執行時間。
  - `llm_tokens_total{type=prompt|completion,model}`：Token 消耗。
  - `agent_runs_total{status}`、`a2a_call_duration`、`mcp_call_duration`。
- **Log**
  - 結構化 JSON，**自動注入 `trace_id` / `span_id`** 以與 trace 關聯。
  - 落點：複用 Hook / Middleware pipeline 的邊界（agent / tool / mcp start-end、auth 決策、session_stop、error），不另造機制。
- **可靠性（硬需求：監控失敗不可影響 main agent 運作）**
  1. 所有 o11y 呼叫包在 fail-safe wrapper：catch 後吞掉，絕不往主流程 raise。
  2. 非同步批次匯出（BatchSpanProcessor / PeriodicExportingMetricReader），export 延遲不阻塞主流程。
  3. 佇列設上限、滿則 drop、export timeout 設短。
  4. 可經 config 整層關閉。

## Config
將以下資訊 config 化：
- LLM：`api_key`、`base_url`、`model`、`temperature`、`system_prompt`。
- Auth：auth 端點 URL。
- Observability：`otel_endpoint`、`sampling_ratio`、`o11y_enabled`、`cid`、`agent_version`。

## MVP 範圍與非目標 (Scope / Non-Goals)
- **In scope**：DeepAgent 驅動、OpenAI-compatible LLM、build_agent / add_skill / add_mcp、A2A（client + server，Agent Card 發現）、Hook / Middleware、auth hook（mock）、Observability。
- **Non-goals（本 MVP 不做）**：
  - Claude / Harness 框架 adapter（僅預留抽象層，不實作）。
  - `SecureAgent` 安全外殼包裝層。
  - 對話級 / 跨呼叫的 session 持久化（checkpointer）。
  - skill-registry、auth 端點的正式實作（皆 mock）。

## 驗收範例 (Acceptance Example)
Example Agent（用 SDK 建立的示範 Agent，用於驗證功能）。需示範並驗證以下每一項：
- 以 `build_agent` 建立 DeepAgent、對 OpenAI-compatible 端點完成一次 `invoke` 與一次 `stream`。
- `add_skill`（mock）與 `add_mcp`（stdio 與 HTTP/SSE 各一）成功掛載並被 agent 呼叫。
- Hook 於 llm / skill / mcp 前後觸發；auth hook（mock）攔截並放行 / 拒絕；收到 `session_stop` 時中止該輪。
- 作為 A2A server 被另一 agent（client）呼叫，經 Agent Card 發現、入站 auth 驗證、streaming 推送成功。
- Observability：Trace 於 Langfuse 可見完整 tree；Metrics 有 tool 次數 / 時間與 token；Log 帶 trace 關聯與 `cid` / `agent_version`；刻意讓 o11y 匯出失敗，確認 main agent 不受影響。
