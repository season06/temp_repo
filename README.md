# agent_template

輕量、高擴充性、支援多框架 (framework-agnostic) 的 AI Agent 開發套件 (SDK)。以統一介面快速構建、組合並部署 AI Agent;MVP 階段以 **DeepAgent** 為驅動。

## 設計原則

「**統一建構、注入式儀器化、執行期回歸原生**」:

- **統一建構** — 所有框架共用最小介面 `get_provider_builder` / `AgentBuilder.add_mcp` / `add_skill`,回傳**原生 agent 物件**。
- **注入式儀器化** — Hook / Auth / Observability 於建構期注入(對 DeepAgent = 掛 middleware);未來每個框架的 adapter 各自翻譯。
- **執行期回歸原生** — `invoke` / `stream` 等直接用該框架的原生 API。

LLM 只支援 **OpenAI-compatible** 端點(地端模型:`base_url` + `api_key` + `model`)。安全 / 驗證 / Observability 皆 **fail-safe**(失敗不影響 main agent)。

## 安裝

環境為 Python 3.14（externally-managed;venv 無內建 pip):

```bash
python3 -m venv --without-pip .venv
python3 -m pip --python .venv/bin/python install \
    deepagents==0.6.12 langchain-openai==1.3.3 langchain-mcp-adapters==0.3.0 \
    pydantic pyyaml \
    opentelemetry-sdk==1.43.0 opentelemetry-exporter-otlp-proto-http==1.43.0 \
    openinference-instrumentation-langchain==0.1.67 a2a-sdk==1.1.0 httpx pytest
```

（相依皆列於 `pyproject.toml`;`--python` 需放在 `install` 之前。）

## 快速開始

```python
from agent_template.config import Config
from agent_template.core import AgentBuilder

# 從 config.yaml(結構)+ .env(secrets/端點)一次載入
config = Config.load("config.yaml", ".env")
agent = AgentBuilder(config).build()          # 回傳原生 DeepAgent 物件;skills/mcps 由 config 帶入
result = agent.invoke({"messages": [("user", "Hello!")]})
print(result["messages"][-1].content)
```

> `Config.load()` 讀 `config.yaml` 取 `agent` / `skills__*` / `mcps__*`,讀 `.env` 取 LLM 憑證、Observability、Auth 端點。也可 `Config.load_from_yaml(path)` / `Config.load_from_env(path)` 分開載入。

> 掛載 MCP tool 後,agent 必須以 **`ainvoke` / `astream`** 執行(MCP tool 為 async-only)。

## 專案結構

依關注點分成子套件,每個子套件的 `__init__.py` 都 re-export 其公開名稱,所以匯入時用子套件路徑即可(如 `from agent_template.hooks import Hook`):

```
agent_template/
├── __init__.py            # 版本
├── config.py              # 每個 section 一個 pydantic model + Config.load
├── config.yaml            # 結構設定(agent / skills__* / mcps__*)
├── .env.example           # secrets/端點(LLM_* / OTEL_* / AUTH_ENDPOINT)
├── core/                  # Agent 建構核心
│   ├── factory.py         #   build_deepagent(注入 middleware)+ get_provider_builder(唯一分派點)
│   └── builder.py         #   AgentBuilder(累加式 add_mcp/add_skill/add_hook)
├── hooks/                 # Hook / Middleware 機制
│   ├── base.py            #   Hook、HookContext、StopRound
│   ├── middleware.py      #   HookMiddleware(翻譯成 langchain middleware 的唯一模組)
│   └── session.py         #   is_session_stop / make_session_stop_metadata
├── auth/                  # 權限驗證
│   └── clients.py         #   AuthClient / HttpAuthClient / AuthHook / Async* 版
├── tools/                 # Skill 與 MCP 接入
│   ├── mcp.py             #   load_mcp_tools / load_configured_mcp_tools(config→connection 翻譯)
│   └── skills.py          #   load_skill_tools(從 @tool python 檔載入)
├── observability/         # OpenTelemetry 監控
│   └── otel.py            #   setup_observability / ObservabilityMiddleware / …
└── a2a/                   # Agent-to-Agent(標準 a2a-sdk)
    ├── server.py          #   build_agent_card / AgentA2AExecutor / build_a2a_app
    └── client.py          #   call_agent

examples/agent.py          # 串起全部功能的示範
tests/                     # 單元 + 端到端驗收(tests/test_acceptance.py)
docs/superpowers/          # 設計規格書 (specs/) 與分階段實作計畫 (plans/)
```

**匯入位置一覽:** `agent_template.config`(Config/LLMConfig/AgentSettings/SkillsConfig/McpsConfig/ObservabilityConfig/AuthConfig)、`agent_template.core`(get_provider_builder/AgentBuilder/register_provider)、`agent_template.hooks`(Hook/HookMiddleware/…)、`agent_template.auth`(AuthHook/…)、`agent_template.tools`(load_mcp_tools/load_skill_tools/…)、`agent_template.observability`(setup_observability/…)、`agent_template.a2a`(build_a2a_app/call_agent/…)。

## 核心功能

### 1. Config

每個來源 section 對應一個 pydantic model,頂層 `Config` 組合起來:

| Section | 來源 | 欄位 |
|---|---|---|
| `LLMConfig` | `.env` | `api_key` / `base_url` / `model` / `temperature`(`LLM_*`) |
| `ObservabilityConfig` | `.env` | `enabled` / `endpoint` / `sampling_ratio` / `service_name` / `cid` / `agent_version`(`OTEL_*` / `SERVICE_NAME` / `CID` / `AGENT_VERSION`) |
| `AuthConfig` | `.env` | `endpoint`(`AUTH_ENDPOINT`) |
| `AgentSettings` | `config.yaml` `agent` | `provider` / `system_prompt` |
| `SkillsConfig` | `config.yaml` `skills__*` | `local: [LocalSkill(name, path)]` / `remote: RemoteRef` |
| `McpsConfig` | `config.yaml` `mcps__*` | `local: [LocalMcp(name, transport, path, func)]` / `remote: RemoteRef` |

- `Config.load(yaml_path, env_path)` — 合併兩個來源(最常用)。
- `Config.load_from_yaml(path)` / `Config.load_from_env(path)` — 只載入該來源的 sections;其餘用預設。
- 每個 section model 各自帶 `load_from_yaml(data)` 或 `load_from_env(env)`。`.env` 由 `python-dotenv` 解析,實際環境變數優先於檔案值。

**Provider 分派:** `config.agent.provider`(預設 `deepagent`)決定 `get_provider_builder`(唯一分派點)選用哪個具體 build 函式;`AgentBuilder.build` 載入 tools 後即委派給它。framework-agnostic 的接點就在這:

```python
from agent_template.core import register_provider

register_provider("my-framework", my_build_fn)   # 簽章同 build_deepagent(config, hooks, tools, observability, model)
# config.agent.provider = "my-framework" 時,builder 就會走 my_build_fn
```

未知 provider 會拋 `ValueError`(列出支援清單)。

### 2. Hook / Middleware

實作 `agent_template.hooks.Hook` 子類,覆寫需要的生命週期節點:

```python
from agent_template.hooks import Hook, StopRound

class MyHook(Hook):
    def before_tool(self, context):   # before_llm / after_llm / before_tool / after_tool
        if not_allowed(context.tool_name):
            return StopRound(reason="blocked")   # 中止該輪

agent = AgentBuilder(config).add_hook(MyHook()).build()
```

- 回傳 `None` 繼續、回傳 `StopRound` 中止該輪。
- 內建 **session_stop**:tool/mcp 或 LLM 回應帶 `{"status": "session_stop"}`(`response_metadata` / `additional_kwargs`)即中止該輪。偵測點在 `agent_template.session.is_session_stop`(單點可換)。

### 3. Authentication

`AuthHook` 在 tool 執行前打 auth 端點,非 200 即中止該輪(fail-closed):

```python
from agent_template.auth import AuthHook, HttpAuthClient

agent = (AgentBuilder(config)
         .add_hook(AuthHook(HttpAuthClient(config.auth.endpoint)))
         .build())
```

A2A server 入站用 **async** 版 `AsyncHttpAuthClient`(見下)。`AuthClient` 為單點可換介面。

### 4. Skill 與 MCP

skills 與 mcps 直接來自 `config`(`config.yaml` 的 `skills__local` / `mcps__local`);`add_skill` / `add_mcp` 則是在 config 帶入的清單之後**追加**。從 deepagent 的角度,兩者最終都是餵給 `create_deep_agent(tools=...)` 的 langchain tool。

```python
config = Config.load("config.yaml", ".env")   # 已含 skills/mcps
agent = (AgentBuilder(config)
         .add_mcp("extra", "streamable_http", "http://host/mcp")   # 追加一個 MCP server
         .add_skill("greet", "./skills/greet.py")                  # 追加一個本地 skill 檔
         .build())
```

- `add_mcp(name, transport, path, func=None)` — `transport` 為 `stdio`(path 為要執行的 `.py`)或 `streamable_http`(path 為 URL);內部翻譯成 `langchain-mcp-adapters` connection。`func` 非空則只保留該 server 內指定名稱的 tool。
- `add_skill(name, path)` — `path` 指向一個含 `@tool` 的 python 檔;載入時收集檔內所有 langchain tool。
- 遠端 registry(`skills__remote` / `mcps__remote`)MVP 尚未接。

### 5. Observability

基於 OpenTelemetry(trace 走 `openinference` langchain instrumentation 自動產生完整 tree;metrics/log 自建);全 fail-safe、可整層關閉:

```python
from agent_template.observability import setup_observability

obs = setup_observability(config.observability)   # 一次,app 啟動時(冪等)
agent = AgentBuilder(config, observability=obs).build()
```

- Metrics:`tool_calls_total{tool,status}`、`tool_call_duration_seconds{tool}`、`llm_tokens_total{type,model}`、`agent_runs_total{status}`。
- Resource 帶 `service.name` / `cid` / `agent.version` / `framework`。
- 非同步匯出(OTLP → collector;Langfuse 消費);`o11y_enabled=False` 或設定失敗 → no-op;`shutdown_observability()` 拆管線。

### 6. Agent-to-Agent (A2A)

用官方 `a2a-sdk`,標準協定(Agent Card + JSON-RPC),同一 agent 兼具 server 與 client:

```python
# server
from agent_template.a2a import build_agent_card, build_a2a_app
from agent_template.auth import AsyncHttpAuthClient
import uvicorn

card = build_agent_card(name="my-agent", url="http://myhost:8000/")
app = build_a2a_app(agent, card, auth_client=AsyncHttpAuthClient(config.auth.endpoint))
uvicorn.run(app, host="0.0.0.0", port=8000)

# client(呼叫別的 agent)
import httpx
from agent_template.a2a import call_agent
async with httpx.AsyncClient() as hc:
    reply = await call_agent(hc, "http://myhost:8000", "hi")
```

- Agent Card 於 `/.well-known/agent-card.json`;client 經 `A2ACardResolver` 發現。
- 入站請求共用 auth（async,於 server 邊界驗證;未過回 `unauthorized`)。

## Example Agent

`examples/agent.py::build_example_agent(config, observability=None, auth_client=None, extra_hooks=None)` 串起 auth / MCP / skill / observability / hooks 的完整示範(skills/mcps 由 `config` 帶入);`python -m examples.agent` 用 `Config.load()` 有真實用法範例。

## 測試

```bash
.venv/bin/python -m pytest          # 122 tests
```

`tests/test_acceptance.py` 對照本 README 各功能逐點端到端驗證(用假模型 / 真實 stdio MCP 子行程 / in-process A2A / in-memory OTel,不需真實 LLM 或外部服務)。

## 已知的 MVP 後續（尚未實作）

- A2A incremental token streaming(目前為單一回應;client 仍走標準 async-iterator)。
- 真實 auth 契約與 A2A 入站 caller identity(目前 mock)。
- 真實 LLM 端點 / Langfuse 呈現 / MCP HTTP transport 的整合測試(機制已於單元測試涵蓋)。
- Observability:export timeout 調短、`agent_runs_total` 記錄 error 狀態、擴大 log 邊界覆蓋。
