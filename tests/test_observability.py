from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from agent_template.config import Config
from agent_template import observability as obs_mod
from agent_template.observability import build_resource, create_instruments, setup_observability


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
    from openinference.instrumentation.langchain import LangChainInstrumentor
    handle = setup_observability(Config(o11y_enabled=True, otel_endpoint="http://localhost:4318"))
    try:
        assert handle.enabled is True
        assert set(handle.instruments.keys()) == {"tool_calls", "tool_duration", "llm_tokens", "agent_runs"}
    finally:
        LangChainInstrumentor().uninstrument()
