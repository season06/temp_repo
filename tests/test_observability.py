from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from agent_template.config import Config
from agent_template import observability as obs_mod
from agent_template.observability import build_resource, create_instruments, setup_observability, shutdown_observability


def _in_memory_meter():
    reader = InMemoryMetricReader()
    return MeterProvider(metric_readers=[reader]).get_meter("test"), reader


def test_build_resource_carries_attributes():
    cfg = Config(cid="proj-9", agent_version="1.2.3", service_name="svc")
    resource = build_resource(cfg)
    assert resource.attributes.get("service.name") == "svc"
    assert resource.attributes.get("cid") == "proj-9"
    assert resource.attributes.get("agent.version") == "1.2.3"


def test_create_instruments_returns_four_named():
    meter, _ = _in_memory_meter()
    instruments = create_instruments(meter)
    assert set(instruments.keys()) == {"tool_calls", "tool_duration", "llm_tokens", "agent_runs"}


def test_setup_disabled_returns_noop_handle():
    handle = setup_observability(Config(o11y_enabled=False))
    assert handle.enabled is False
    assert handle.instruments == {}


def test_setup_failure_is_swallowed(monkeypatch):
    # 讓 setup 過程拋錯 → 必須回傳 degraded handle,不可 raise
    def boom(*a, **k):
        raise RuntimeError("otel broken")

    monkeypatch.setattr(obs_mod, "TracerProvider", boom)
    handle = setup_observability(Config(o11y_enabled=True, otel_endpoint="http://localhost:4318"))
    assert handle.enabled is False


def test_setup_enabled_builds_instruments_then_uninstrument():
    handle = setup_observability(Config(o11y_enabled=True, otel_endpoint="http://localhost:4318"))
    try:
        assert handle.enabled is True
        assert set(handle.instruments.keys()) == {"tool_calls", "tool_duration", "llm_tokens", "agent_runs"}
    finally:
        shutdown_observability()


def test_metrics_recorded_end_to_end_under_ainvoke():
    import asyncio
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool
    from deepagents import create_deep_agent
    from agent_template.observability import ObservabilityMiddleware
    from tests.fakes import FakeToolModel

    meter, reader = _in_memory_meter()
    instruments = create_instruments(meter)

    @tool
    def ping(x: str) -> str:
        """p"""
        return "pong:" + x

    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "ping", "args": {"x": "h"}, "id": "c1"}]),
        AIMessage(content="done", usage_metadata={"input_tokens": 3, "output_tokens": 5, "total_tokens": 8}),
    ])
    mw = ObservabilityMiddleware(instruments)
    agent = create_deep_agent(model=model, tools=[ping], system_prompt="x", middleware=[mw])
    asyncio.run(agent.ainvoke({"messages": [("user", "go")]}))

    totals = {}
    for rm in reader.get_metrics_data().resource_metrics:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                # tool_duration is a histogram (no .value); skip non-counter data points.
                totals[m.name] = sum(dp.value for dp in m.data.data_points if hasattr(dp, "value"))
    assert totals.get("tool_calls_total") == 1
    assert totals.get("agent_runs_total") == 1
    assert totals.get("llm_tokens_total") == 8  # 3 input + 5 output


def test_failing_instrument_does_not_break_agent():
    import asyncio
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool
    from deepagents import create_deep_agent
    from agent_template.observability import ObservabilityMiddleware
    from tests.fakes import FakeToolModel

    class _Boom:
        def add(self, *a, **k):
            raise RuntimeError("otel down")

        def record(self, *a, **k):
            raise RuntimeError("otel down")

    instruments = {"tool_calls": _Boom(), "tool_duration": _Boom(), "llm_tokens": _Boom(), "agent_runs": _Boom()}

    @tool
    def ping(x: str) -> str:
        """p"""
        return "pong:" + x

    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "ping", "args": {"x": "h"}, "id": "c1"}]),
        AIMessage(content="done"),
    ])
    mw = ObservabilityMiddleware(instruments)
    agent = create_deep_agent(model=model, tools=[ping], system_prompt="x", middleware=[mw])
    out = asyncio.run(agent.ainvoke({"messages": [("user", "go")]}))
    assert out["messages"][-1].content == "done"  # 監控失敗不影響 main agent


def test_disabled_instruments_noop():
    from agent_template.observability import ObservabilityMiddleware
    mw = ObservabilityMiddleware({})

    class _Req:
        tool_call = {"name": "ping", "args": {}, "id": "c1"}

    from langchain_core.messages import ToolMessage
    result = mw.wrap_tool_call(_Req(), lambda r: ToolMessage(content="ok", tool_call_id="c1", name="ping"))
    assert result.content == "ok"  # no-op passthrough


def test_setup_is_idempotent_and_shutdown_resets():
    from agent_template.observability import setup_observability, shutdown_observability, get_logger
    cfg = Config(o11y_enabled=True, otel_endpoint="http://localhost:4318")
    logger = get_logger()
    before = len(logger.handlers)
    h1 = setup_observability(cfg)
    h2 = setup_observability(cfg)
    try:
        assert h1 is h2                              # idempotent: same handle
        assert len(logger.handlers) == before + 1    # only one handler despite two setups
    finally:
        shutdown_observability()
    assert len(logger.handlers) == before            # shutdown removed the handler
