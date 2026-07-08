# P7 — Example Agent & Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供一個用 SDK 串起全部功能的 **Example Agent**,並以**驗收測試**逐一證明 req.md 的每個驗證點,收尾整個 MVP。

**Architecture:** 先加一個**模型注入 seam**(`build_agent(..., model=None)`)讓全鏈路可用假模型端到端測試(同時是「自帶已設定模型」的實用能力)。`examples/example_agent.py::build_example_agent` 用 `AgentBuilder` 把 auth hook + MCP + skill + observability + hooks 串起來。`tests/test_acceptance.py` 對照 req.md「驗收範例」逐點端到端驗證(用 fakes / in-process,不需真實 LLM/Langfuse/auth server)。

**Tech Stack:** 既有全部模組 + pytest;fakes(`tests/fakes.py`、`tests/mcp_server.py`)、in-memory OTel、httpx ASGITransport。

## Global Constraints

- **前置**：P0–P6 完成(HEAD `16408ec`,97 tests)。
- **已驗證(spike)**：`HookMiddleware([RecHook, AuthHook]) + ObservabilityMiddleware` 三者可**同時**組在一個 agent;`ainvoke` 下 hooks 全觸發、metrics 記到(tool_calls/llm_tokens/agent_runs);`agent.stream(...)`(fake model、無 MCP)可產出 chunk;`after_llm` 回 `StopRound` 可中止該輪。MCP tool 需 `ainvoke`(async-only)。
- **模型注入**:`build_agent(config, ..., model=None)` —— `model` 有值就直接用它(跳過 `ChatOpenAI`);`None` 走 `_build_llm(config)`。與既有呼叫相容。
- **驗收用 fakes**:LLM 用 `tests.fakes.FakeToolModel`;MCP 用 `tests/mcp_server.py`(真實 stdio 子行程);skill 用 `MockSkillRegistry`;auth 用注入的 fake client;o11y 用 in-memory MeterProvider + `ObservabilityMiddleware`。真實端點/Langfuse/auth server 不在測試內(example 的 `__main__` 走真實設定,不被測試驅動)。
- **example 可 import**:`examples/` 為 package(`examples/__init__.py`),測試以 `from examples.example_agent import build_example_agent` 取用(repo 根在 sys.path)。
- **型別註記慣例**:只標註 dict/list;不 import `typing`;不標註 primitive;plain class + `__init__`。
- **執行測試**:`.venv/bin/python -m pytest`。
- **Commit 時機**:commit 為執行期動作,由使用者決定何時執行本計畫。

---

### Task 1: 模型注入 seam（`build_agent(..., model=None)`）

**Files:**
- Modify: `agent_template/factory.py`
- Modify: `agent_template/builder.py`
- Test: `tests/test_factory.py`、`tests/test_builder.py`（同檔追加）

**Interfaces:**
- Produces: `build_agent(config, hooks=None, tools=None, observability=None, model=None)` —— `model` 非 None 時用它,否則 `_build_llm(config)`。`AgentBuilder(config, skill_registry=None, observability=None, model=None)`,`build()` 傳 `model=self._model`。

- [ ] **Step 1: 追加測試（會失敗）**

Append to `tests/test_factory.py`:

```python
def test_build_agent_uses_injected_model_bypassing_chatopenai(monkeypatch):
    calls = {}

    def boom(**k):
        raise AssertionError("ChatOpenAI must not be built when model is injected")

    monkeypatch.setattr(factory, "ChatOpenAI", boom)
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")
    factory.build_agent(AgentConfig(api_key="k", base_url="b", model="m"), model="INJECTED")
    assert calls["model"] == "INJECTED"


def test_build_agent_builds_llm_when_no_model(monkeypatch):
    calls = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")
    factory.build_agent(AgentConfig(api_key="k", base_url="b", model="m"))
    assert calls["model"] == "LLM"
```

Append to `tests/test_builder.py`:

```python
def test_builder_passes_injected_model(monkeypatch):
    captured = {}
    monkeypatch.setattr(bmod, "load_mcp_tools", lambda conns: [])
    monkeypatch.setattr(bmod, "build_agent",
                        lambda config, hooks, tools, observability=None, model=None: captured.update(model=model) or "AGENT")
    AgentBuilder(_cfg(), model="FAKE").build()
    assert captured["model"] == "FAKE"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_factory.py tests/test_builder.py -k "injected_model or builds_llm_when_no_model" -v`
Expected: FAIL（`build_agent`/`AgentBuilder` 尚不接受 `model`）。

- [ ] **Step 3: 修改 `build_agent`**

Edit `agent_template/factory.py` 的 `build_agent`（新增 `model` 參數 + 分支）：

```python
def build_agent(config, hooks=None, tools=None, observability=None, model=None):
    """建構並回傳原生 DeepAgent 物件（執行期回歸原生,無包裝）。
    model: 若提供則直接使用(自帶已設定模型),否則由 config 建 ChatOpenAI。"""
    llm = model if model is not None else _build_llm(config)
    middleware = [HookMiddleware(hooks)] if hooks else []
    if observability is not None and observability.enabled:
        middleware.append(ObservabilityMiddleware(observability.instruments, observability.logger, config.model))
    return create_deep_agent(
        model=llm,
        tools=tools or [],
        system_prompt=config.system_prompt,
        middleware=middleware,
    )
```

- [ ] **Step 4: 修改 `AgentBuilder`**

Edit `agent_template/builder.py`:`__init__` 新增 `model=None`、存 `self._model = model`;`build()` 的呼叫改為帶 `model=self._model`。

```python
    def __init__(self, config, skill_registry=None, observability=None, model=None):
        self._config = config
        self._registry = skill_registry or MockSkillRegistry()
        self._observability = observability
        self._model = model
        self._mcp_connections = {}
        self._skill_ids = []
        self._hooks = []
```

`build()` 尾行:

```python
        return build_agent(self._config, hooks=self._hooks, tools=tools, observability=self._observability, model=self._model)
```

- [ ] **Step 5: 跑測試確認通過（含既有不退化）**

Run: `.venv/bin/python -m pytest tests/test_factory.py tests/test_builder.py -v`
Expected: PASS（既有 + 新增全綠;新參數具預設值,向後相容)。

- [ ] **Step 6: Commit**

```bash
cd /home/xizhen/文件/temp_repo
git add agent_template/factory.py agent_template/builder.py tests/test_factory.py tests/test_builder.py
git commit -m "feat: add model-injection seam to build_agent and AgentBuilder"
```

---

### Task 2: Example Agent（`examples/example_agent.py`）

**Files:**
- Create: `examples/__init__.py`（空）
- Create: `examples/example_agent.py`
- Test: `tests/test_example_agent.py`

**Interfaces:**
- Produces: `build_example_agent(config, model=None, mcp=None, skill_ids=None, skill_registry=None, observability=None, auth_client=None, extra_hooks=None)` —— 用 `AgentBuilder` 串:AuthHook(auth_client 或 `HttpAuthClient(config.auth_endpoint)`)+ extra_hooks + 每個 mcp(dict name→connection)+ 每個 skill_id;回傳原生 agent。

- [ ] **Step 1: 寫測試（會失敗）**

Create `tests/test_example_agent.py`:

```python
import asyncio

from langchain_core.messages import AIMessage

from agent_template.config import AgentConfig
from agent_template.skills import Skill, MockSkillRegistry
from examples.example_agent import build_example_agent
from tests.fakes import FakeToolModel


class _Allow:
    def verify(self, context):
        return True


def _cfg():
    return AgentConfig(api_key="k", base_url="http://x/v1", model="m")


def test_build_example_agent_runs_skill_tool():
    reg = MockSkillRegistry({"greet": Skill("greet", "greeting", "hi-from-skill")})
    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "greet", "args": {}, "id": "c1"}]),
        AIMessage(content="done"),
    ])
    agent = build_example_agent(_cfg(), model=model, skill_ids=["greet"],
                                skill_registry=reg, auth_client=_Allow())
    out = asyncio.run(agent.ainvoke({"messages": [("user", "hello")]}))
    contents = [str(getattr(m, "content", None)) for m in out["messages"]]
    assert any("hi-from-skill" in c for c in contents)  # skill tool executed
    assert out["messages"][-1].content == "done"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_example_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'examples'`。

- [ ] **Step 3: 實作 example**

Create `examples/__init__.py`（空檔）。

Create `examples/example_agent.py`:

```python
"""示範 Agent:用 agent_template 串起 auth / MCP / skill / observability / hooks。"""

from agent_template.auth import AuthHook, HttpAuthClient
from agent_template.builder import AgentBuilder


def build_example_agent(config, model=None, mcp=None, skill_ids=None, skill_registry=None,
                        observability=None, auth_client=None, extra_hooks=None):
    """組出一個示範 agent 並回傳原生物件。

    config: AgentConfig。model: 可注入自帶模型(測試/BYO)。
    mcp: dict[name -> connection];skill_ids: list[str](需搭配 skill_registry)。
    observability: setup_observability 的 handle;auth_client: 覆寫預設 HttpAuthClient。
    extra_hooks: 額外的 Hook 清單。
    """
    builder = AgentBuilder(config, skill_registry=skill_registry, observability=observability, model=model)
    builder.add_hook(AuthHook(auth_client if auth_client is not None else HttpAuthClient(config.auth_endpoint)))
    for hook in (extra_hooks or []):
        builder.add_hook(hook)
    for name, connection in (mcp or {}).items():
        builder.add_mcp(name, connection)
    for skill_id in (skill_ids or []):
        builder.add_skill(skill_id)
    return builder.build()


if __name__ == "__main__":
    # 真實用法(需可用的 OpenAI-compatible 端點、auth 端點;o11y 選用):
    from agent_template.config import AgentConfig, Config
    from agent_template.observability import setup_observability

    runtime = Config.from_env()
    agent_config = AgentConfig(
        api_key="sk-...", base_url="http://localhost:8000/v1", model="qwen",
        system_prompt="You are a helpful agent.",
    )
    agent = build_example_agent(
        agent_config,
        observability=setup_observability(runtime),
        mcp={"local": {"transport": "stdio", "command": "python", "args": ["my_mcp_server.py"]}},
    )
    result = agent.invoke({"messages": [("user", "Hello!")]})
    print(result["messages"][-1].content)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_example_agent.py -v`
Expected: PASS（1 passed;skill tool 被 agent 呼叫、回傳 done）。

- [ ] **Step 5: Commit**

```bash
cd /home/xizhen/文件/temp_repo
git add examples/__init__.py examples/example_agent.py tests/test_example_agent.py
git commit -m "feat: add Example Agent wiring auth/mcp/skill/observability"
```

---

### Task 3: 驗收測試（`tests/test_acceptance.py`）

**Files:**
- Create: `tests/test_acceptance.py`

**Interfaces:**
- Consumes: 既有全部模組 + fakes。無新產出;純驗收。

對照 req.md「驗收範例」逐點端到端驗證。

- [ ] **Step 1: 寫驗收測試**

Create `tests/test_acceptance.py`:

```python
import asyncio
import os
import sys

import httpx
from langchain_core.messages import AIMessage

from agent_template.config import AgentConfig
from agent_template.builder import AgentBuilder
from agent_template.hooks import Hook, StopRound
from agent_template.auth import AuthHook
from agent_template.skills import Skill, MockSkillRegistry
from agent_template.observability import ObservabilityMiddleware, create_instruments
from agent_template._middleware import HookMiddleware
from agent_template.a2a_server import build_agent_card, build_a2a_app
from agent_template.a2a_client import call_agent
from tests.fakes import FakeToolModel

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from deepagents import create_deep_agent

BASE = "http://test"


def _cfg():
    return AgentConfig(api_key="k", base_url="http://x/v1", model="m", system_prompt="x")


class _Allow:
    def verify(self, context):
        return True


class _Deny:
    def verify(self, context):
        return False


def _metric_totals(reader):
    totals = {}
    for rm in reader.get_metrics_data().resource_metrics:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                for dp in m.data.data_points:
                    if hasattr(dp, "value"):
                        totals[m.name] = totals.get(m.name, 0) + dp.value
    return totals


# req.md 驗收點 1:build + invoke + stream
def test_acceptance_build_invoke_and_stream():
    model = FakeToolModel(scripted=[AIMessage(content="hello-response")])
    agent = AgentBuilder(_cfg(), model=model).build()
    out = agent.invoke({"messages": [("user", "hi")]})
    assert out["messages"][-1].content == "hello-response"

    stream_model = FakeToolModel(scripted=[AIMessage(content="streamed")])
    stream_agent = AgentBuilder(_cfg(), model=stream_model).build()
    chunks = list(stream_agent.stream({"messages": [("user", "hi")]}))
    assert len(chunks) > 0


# req.md 驗收點 2:add_skill(mock) + add_mcp(stdio) 被 agent 呼叫
def test_acceptance_mcp_and_skill_tools_are_called():
    server = os.path.join(os.path.dirname(__file__), "mcp_server.py")
    reg = MockSkillRegistry({"greet": Skill("greet", "greeting", "hi-from-skill")})
    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "echo", "args": {"text": "x"}, "id": "c1"}]),
        AIMessage(content="", tool_calls=[{"name": "greet", "args": {}, "id": "c2"}]),
        AIMessage(content="done"),
    ])
    agent = (AgentBuilder(_cfg(), skill_registry=reg, model=model)
             .add_mcp("t", {"transport": "stdio", "command": sys.executable, "args": [server]})
             .add_skill("greet")
             .build())
    out = asyncio.run(agent.ainvoke({"messages": [("user", "go")]}))
    contents = [str(getattr(m, "content", None)) for m in out["messages"]]
    assert any("echo:x" in c for c in contents)         # MCP tool ran
    assert any("hi-from-skill" in c for c in contents)  # skill tool ran


# req.md 驗收點 3a:hooks 於 llm/tool 前後觸發 + auth allow
def test_acceptance_hooks_fire_and_auth_allows():
    seen = []

    class Rec(Hook):
        def before_llm(self, c): seen.append("before_llm")
        def after_llm(self, c): seen.append("after_llm")
        def before_tool(self, c): seen.append("before_tool")
        def after_tool(self, c): seen.append("after_tool")

    from langchain_core.tools import tool

    @tool
    def ping(x: str) -> str:
        """p"""
        return "pong"

    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "ping", "args": {"x": "h"}, "id": "c1"}]),
        AIMessage(content="done"),
    ])
    agent = create_deep_agent(model=model, tools=[ping], system_prompt="x",
                              middleware=[HookMiddleware([Rec(), AuthHook(_Allow())])])
    asyncio.run(agent.ainvoke({"messages": [("user", "go")]}))
    assert "before_llm" in seen and "after_llm" in seen
    assert "before_tool" in seen and "after_tool" in seen


# req.md 驗收點 3b:auth deny 擋工具並中止該輪
def test_acceptance_auth_deny_blocks_tool_and_halts():
    ran = []
    from langchain_core.tools import tool

    @tool
    def act(x: str) -> str:
        """a"""
        ran.append(x)
        return "did"

    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "act", "args": {"x": "h"}, "id": "c1"}]),
        AIMessage(content="should-not-reach"),
    ])
    agent = create_deep_agent(model=model, tools=[act], system_prompt="x",
                              middleware=[HookMiddleware([AuthHook(_Deny())])])
    out = asyncio.run(agent.ainvoke({"messages": [("user", "go")]}))
    contents = [str(getattr(m, "content", None)) for m in out["messages"]]
    assert ran == []
    assert "should-not-reach" not in contents


# req.md 驗收點 3c:session_stop 中止該輪
def test_acceptance_session_stop_halts_round():
    class Stopper(Hook):
        def after_llm(self, c):
            return StopRound(reason="stop")

    model = FakeToolModel(scripted=[AIMessage(content="first"), AIMessage(content="should-not-reach")])
    agent = create_deep_agent(model=model, tools=[], system_prompt="x",
                              middleware=[HookMiddleware([Stopper()])])
    out = asyncio.run(agent.ainvoke({"messages": [("user", "go")]}))
    contents = [str(getattr(m, "content", None)) for m in out["messages"]]
    assert "should-not-reach" not in contents


# req.md 驗收點 4:A2A server 被 client 呼叫(card 發現 + 入站 auth)
def test_acceptance_a2a_roundtrip_and_inbound_auth():
    def _agent(reply):
        return create_deep_agent(model=FakeToolModel(scripted=[AIMessage(content=reply)]), tools=[], system_prompt="x")

    async def _call(app, text):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as hc:
            return await call_agent(hc, BASE, text)

    ok_app = build_a2a_app(_agent("a2a-reply"), build_agent_card(name="Svc", url=BASE + "/"))
    assert asyncio.run(_call(ok_app, "ping")) == "a2a-reply"

    class _AsyncDeny:
        async def verify(self, context):
            return False

    deny_app = build_a2a_app(_agent("secret"), build_agent_card(name="Svc", url=BASE + "/"), auth_client=_AsyncDeny())
    assert asyncio.run(_call(deny_app, "ping")) == "unauthorized"


# req.md 驗收點 5:o11y 記 metrics + 監控失敗不影響 main agent
def test_acceptance_observability_metrics_and_failsafe():
    from langchain_core.tools import tool

    @tool
    def ping(x: str) -> str:
        """p"""
        return "pong"

    reader = InMemoryMetricReader()
    instruments = create_instruments(MeterProvider(metric_readers=[reader]).get_meter("t"))
    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "ping", "args": {"x": "h"}, "id": "c1"}]),
        AIMessage(content="done", usage_metadata={"input_tokens": 2, "output_tokens": 3, "total_tokens": 5}),
    ])
    agent = create_deep_agent(model=model, tools=[ping], system_prompt="x",
                              middleware=[ObservabilityMiddleware(instruments, model_name="fake")])
    asyncio.run(agent.ainvoke({"messages": [("user", "go")]}))
    totals = _metric_totals(reader)
    assert totals.get("tool_calls_total") == 1
    assert totals.get("agent_runs_total") == 1
    assert totals.get("llm_tokens_total") == 5

    class _Boom:
        def add(self, *a, **k): raise RuntimeError("otel down")
        def record(self, *a, **k): raise RuntimeError("otel down")

    boom = {"tool_calls": _Boom(), "tool_duration": _Boom(), "llm_tokens": _Boom(), "agent_runs": _Boom()}
    model2 = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "ping", "args": {"x": "h"}, "id": "c1"}]),
        AIMessage(content="done"),
    ])
    agent2 = create_deep_agent(model=model2, tools=[ping], system_prompt="x",
                               middleware=[ObservabilityMiddleware(boom)])
    out = asyncio.run(agent2.ainvoke({"messages": [("user", "go")]}))
    assert out["messages"][-1].content == "done"  # 監控失敗不影響 main agent
```

- [ ] **Step 2: 跑驗收測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_acceptance.py -v`
Expected: PASS（7 passed;涵蓋 req.md 驗收範例每一點）。

- [ ] **Step 3: 跑全部測試確認整體綠**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS（P0–P6 + P7 全綠)。

- [ ] **Step 4: Commit**

```bash
cd /home/xizhen/文件/temp_repo
git add tests/test_acceptance.py
git commit -m "test: add end-to-end acceptance suite mapping req.md verification points"
```

---

## Self-Review

- **Spec coverage**（req.md 驗收範例逐點）：
  - build_agent + invoke + stream → `test_acceptance_build_invoke_and_stream` ✅
  - add_skill(mock) + add_mcp(stdio 真實) 被 agent 呼叫 → `test_acceptance_mcp_and_skill_tools_are_called` ✅（HTTP/SSE transport 的**設定**已於 P3 涵蓋;驗收以 stdio 實跑,避免測試起 HTTP server)
  - hooks 前後觸發 + auth allow/deny + session_stop → 三個 `test_acceptance_*` ✅
  - A2A server 被 client 呼叫、card 發現、入站 auth → `test_acceptance_a2a_roundtrip_and_inbound_auth` ✅
  - o11y metrics(tool 次數 + token)+ 監控失敗不影響 main agent → `test_acceptance_observability_metrics_and_failsafe` ✅
  - Example Agent 存在且可用(串 auth/mcp/skill/o11y)→ `examples/example_agent.py` + `test_example_agent` ✅
- **Placeholder scan**：無 TBD/TODO;所有組合(全 middleware 疊加、stream、session_stop、A2A、metrics、fail-safe)皆已 spike 驗證。✅
- **Type consistency**：`build_agent(..., model=None)`、`AgentBuilder(..., model=None)`、`build_example_agent(config, model=None, mcp=None, skill_ids=None, ...)` 在各 Task 與測試一致。✅
- **驗收未涵蓋(誠實記錄)**:真實 OpenAI-compatible 端點的 invoke/stream(需 infra,example `__main__` 提供路徑但不被測試驅動);Langfuse 實際呈現 trace tree(需 SaaS;P5 已驗 instrumentation 產 span);log 的 trace_id/cid 關聯(P5 unit 已驗,驗收未重測);MCP HTTP/SSE transport 實跑(P3 已驗設定映射,驗收用 stdio)。
- **Scope**:此為最終 phase;完成後 MVP 全功能有端到端驗收。P6 遺留(A2A in-band 拒絕、真實 auth identity plumbing、streaming incremental)仍為已文件化的 MVP-後續。✅
