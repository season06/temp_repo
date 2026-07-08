# agent_template

輕量、高擴充性、支援多框架 (framework-agnostic) 的 AI Agent 開發套件 (SDK)。以統一介面快速構建、組合並部署 AI Agent;MVP 階段以 **DeepAgent** 為驅動。

## 設計原則

「**統一建構、注入式儀器化、執行期回歸原生**」:

- **統一建構** — 所有框架共用最小介面 `build_agent` / `AgentBuilder.add_mcp` / `add_skill`,回傳**原生 agent 物件**。
- **注入式儀器化** — Hook / Auth / Observability 於建構期注入(對 DeepAgent = 掛 middleware);未來每個框架的 adapter 各自翻譯。
- **執行期回歸原生** — `invoke` / `stream` 等直接用該框架的原生 API。

LLM 只支援 **OpenAI-compatible** 端點(地端模型:`base_url` + `api_key` + `model`)。安全 / 驗證 / Observability 皆 **fail-safe**(失敗不影響 main agent)。

## 安裝

環境為 Python 3.14（externally-managed;venv 無內建 pip):

```bash
python3 -m venv --without-pip .venv
python3 -m pip --python .venv/bin/python install \
    deepagents==0.6.12 langchain-openai==1.3.3 langchain-mcp-adapters==0.3.0 \
    opentelemetry-sdk==1.43.0 opentelemetry-exporter-otlp-proto-http==1.43.0 \
    openinference-instrumentation-langchain==0.1.67 a2a-sdk==1.1.0 httpx pytest
```

（相依皆列於 `pyproject.toml`;`--python` 需放在 `install` 之前。）

## 快速開始

```python
from agent_template.config import AgentConfig
from agent_template.builder import AgentBuilder

config = AgentConfig(
    api_key="sk-...", base_url="http://localhost:8000/v1",
    model="qwen", system_prompt="You are a helpful agent.",
)
agent = AgentBuilder(config).build()          # 回傳原生 DeepAgent 物件
result = agent.invoke({"messages": [("user", "Hello!")]})
print(result["messages"][-1].content)
```

> 掛載 MCP tool 後,agent 必須以 **`ainvoke` / `astream`** 執行(MCP tool 為 async-only)。

## 核心功能

### 1. Config

- `AgentConfig(api_key, base_url, model, temperature=0.0, system_prompt=None)` — 每個 agent 的 LLM 設定。
- `Config.from_env()` — runtime 設定(`AGENT_AUTH_ENDPOINT`、`AGENT_OTEL_ENDPOINT`、`AGENT_O11Y_ENABLED`、`AGENT_CID`、`AGENT_VERSION`、`AGENT_SERVICE_NAME`、`AGENT_OTEL_SAMPLING_RATIO`)。

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
         .add_hook(AuthHook(HttpAuthClient(runtime_config.auth_endpoint)))
         .build())
```

A2A server 入站用 **async** 版 `AsyncHttpAuthClient`(見下)。`AuthClient` 為單點可換介面。

### 4. Skill 與 MCP

```python
from agent_template.skills import MockSkillRegistry, Skill

registry = MockSkillRegistry({"greet": Skill("greet", "greeting", "hi")})
agent = (AgentBuilder(config, skill_registry=registry)
         .add_mcp("local", {"transport": "stdio", "command": "python", "args": ["server.py"]})
         .add_mcp("remote", {"transport": "streamable_http", "url": "http://host/mcp"})
         .add_skill("greet")
         .build())
```

- `add_mcp(name, connection)` — stdio 或 streamable_http;可重複掛載(同 name 覆蓋)。經 `langchain-mcp-adapters` 載入為 tool。
- `add_skill(skill_id)` — 從 `SkillRegistry` 取得 skill 並轉成 tool(MVP 用 `MockSkillRegistry`)。

### 5. Observability

基於 OpenTelemetry(trace 走 `openinference` langchain instrumentation 自動產生完整 tree;metrics/log 自建);全 fail-safe、可整層關閉:

```python
from agent_template.observability import setup_observability

obs = setup_observability(runtime_config)      # 一次,app 啟動時(冪等)
agent = AgentBuilder(config, observability=obs).build()
```

- Metrics:`tool_calls_total{tool,status}`、`tool_call_duration_seconds{tool}`、`llm_tokens_total{type,model}`、`agent_runs_total{status}`。
- Resource 帶 `service.name` / `cid` / `agent.version` / `framework`。
- 非同步匯出(OTLP → collector;Langfuse 消費);`o11y_enabled=False` 或設定失敗 → no-op;`shutdown_observability()` 拆管線。

### 6. Agent-to-Agent (A2A)

用官方 `a2a-sdk`,標準協定(Agent Card + JSON-RPC),同一 agent 兼具 server 與 client:

```python
# server
from agent_template.a2a_server import build_agent_card, build_a2a_app
from agent_template.auth import AsyncHttpAuthClient
import uvicorn

card = build_agent_card(name="my-agent", url="http://myhost:8000/")
app = build_a2a_app(agent, card, auth_client=AsyncHttpAuthClient(runtime_config.auth_endpoint))
uvicorn.run(app, host="0.0.0.0", port=8000)

# client(呼叫別的 agent)
import httpx
from agent_template.a2a_client import call_agent
async with httpx.AsyncClient() as hc:
    reply = await call_agent(hc, "http://myhost:8000", "hi")
```

- Agent Card 於 `/.well-known/agent-card.json`;client 經 `A2ACardResolver` 發現。
- 入站請求共用 auth（async,於 server 邊界驗證;未過回 `unauthorized`)。

## Example Agent

`examples/example_agent.py::build_example_agent(agent_config, runtime_config=None, ...)` 串起 auth / MCP / skill / observability / hooks 的完整示範;`python -m examples.example_agent` 有真實用法範例。

## 測試

```bash
.venv/bin/python -m pytest          # 110 tests
```

`tests/test_acceptance.py` 對照本 README 各功能逐點端到端驗證(用假模型 / 真實 stdio MCP 子行程 / in-process A2A / in-memory OTel,不需真實 LLM 或外部服務)。

## 已知的 MVP 後續（尚未實作）

- A2A incremental token streaming(目前為單一回應;client 仍走標準 async-iterator)。
- 真實 auth 契約與 A2A 入站 caller identity(目前 mock)。
- 真實 LLM 端點 / Langfuse 呈現 / MCP HTTP transport 的整合測試(機制已於單元測試涵蓋)。
- Observability:export timeout 調短、`agent_runs_total` 記錄 error 狀態、擴大 log 邊界覆蓋。
