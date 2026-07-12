import asyncio
import os

import httpx
from langchain_core.messages import AIMessage

import agent_template.core.factory as factory
from agent_template.config import Config, LLMConfig, AgentSettings
from agent_template.core import AgentBuilder
from agent_template.hooks import Hook, StopRound
from agent_template.auth import AuthHook
from agent_template.observability import ObservabilityMiddleware, create_instruments
from agent_template.hooks import HookMiddleware
from agent_template.a2a import build_agent_card, build_a2a_app
from agent_template.a2a import call_agent
from tests.fakes import FakeToolModel

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from deepagents import create_deep_agent

BASE = "http://test"


SKILL_FIXTURE = os.path.join(os.path.dirname(__file__), "skill_src")


def _cfg():
    from agent_template.config import AuthConfig
    return Config(llm=LLMConfig(api_key="k", base_url="http://x/v1", model="m"),
                  agent=AgentSettings(system_prompt="x"),
                  auth=AuthConfig(endpoint="http://auth/verify"))


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
def test_acceptance_build_invoke_and_stream(monkeypatch):
    monkeypatch.setattr(factory, "HttpAuthClient", lambda ep: _Allow())   # 入口 auth 放行
    ctx = {"identity": "acceptance"}

    model = FakeToolModel(scripted=[AIMessage(content="hello-response")])
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: model)   # config.llm 建出 fake model
    agent = AgentBuilder(_cfg()).build()
    out = agent.invoke({"messages": [("user", "hi")]}, context=ctx)
    assert out["messages"][-1].content == "hello-response"

    stream_model = FakeToolModel(scripted=[AIMessage(content="streamed")])
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: stream_model)
    stream_agent = AgentBuilder(_cfg()).build()
    chunks = list(stream_agent.stream({"messages": [("user", "hi")]}, context=ctx))
    assert len(chunks) > 0


# req.md 驗收點 2:add_mcp(stdio) tool 被呼叫;add_skill 以來源路徑接上 deepagent 原生 skills=(與 tool 不同)
def test_acceptance_mcp_tool_called_and_skill_source_wired(monkeypatch):
    monkeypatch.setattr(factory, "HttpAuthClient", lambda ep: _Allow())   # 入口 auth 放行
    server = os.path.join(os.path.dirname(__file__), "mcp_server.py")

    # MCP tool 真的被執行
    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "echo", "args": {"text": "x"}, "id": "c1"}]),
        AIMessage(content="done"),
    ])
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: model)
    agent = AgentBuilder(_cfg()).add_mcp("t", "stdio", server).build()
    out = asyncio.run(agent.ainvoke({"messages": [("user", "go")]}, context={"identity": "acceptance"}))
    contents = [str(getattr(m, "content", None)) for m in out["messages"]]
    assert any("echo:x" in c for c in contents)         # MCP tool ran

    # skill 以來源路徑接上 deepagent 原生 skills=(非 tool)
    captured = {}
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: captured.update(k) or "AGENT")
    AgentBuilder(_cfg()).add_skill("greet", SKILL_FIXTURE).build()
    assert SKILL_FIXTURE in captured["skills"]


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
    ran = []
    from langchain_core.tools import tool

    @tool
    def act(x: str) -> str:
        """a"""
        ran.append(x)
        return "did"

    class Stopper(Hook):
        def after_llm(self, c):
            return StopRound(reason="stop")

    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "act", "args": {"x": "h"}, "id": "c1"}]),
        AIMessage(content="should-not-reach"),
    ])
    agent = create_deep_agent(model=model, tools=[act], system_prompt="x",
                              middleware=[HookMiddleware([Stopper()])])
    out = asyncio.run(agent.ainvoke({"messages": [("user", "go")]}))
    contents = [str(getattr(m, "content", None)) for m in out["messages"]]
    assert ran == []                       # after_llm StopRound halted BEFORE the tool ran
    assert "should-not-reach" not in contents  # round halted, second LLM turn never reached


# req.md 驗收點 3c':tool/mcp server 回覆 session_stop 狀態 → before_model 捕捉並中止(零 hook)
def test_acceptance_session_stop_from_server_status_halts():
    from langchain_core.tools import tool
    from langchain_core.messages import ToolMessage

    @tool
    def stopper(x: str) -> str:
        """returns a session_stop-tagged ToolMessage"""
        return ToolMessage(content="stop", tool_call_id="c1", name="stopper",
                           response_metadata={"status": "session_stop"})

    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "stopper", "args": {"x": "h"}, "id": "c1"}]),
        AIMessage(content="should-not-reach"),
    ])
    agent = create_deep_agent(model=model, tools=[stopper], system_prompt="x",
                              middleware=[HookMiddleware([])])
    out = asyncio.run(agent.ainvoke({"messages": [("user", "go")]}))
    contents = [str(getattr(m, "content", None)) for m in out["messages"]]
    assert "should-not-reach" not in contents  # server session_stop status caught by before_model, round halted


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

    duration_count = 0
    for rm in reader.get_metrics_data().resource_metrics:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                if m.name == "tool_call_duration_seconds":
                    for dp in m.data.data_points:
                        duration_count += dp.count
    assert duration_count >= 1  # tool 執行時間 histogram recorded

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
