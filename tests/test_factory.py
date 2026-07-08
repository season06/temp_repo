from agent_template import factory
from agent_template.config import AgentConfig


def test_build_llm_passes_openai_compatible_params(monkeypatch):
    captured = {}

    def fake_chat(**kwargs):
        captured.update(kwargs)
        return "LLM"

    monkeypatch.setattr(factory, "ChatOpenAI", fake_chat)
    cfg = AgentConfig(api_key="k", base_url="http://localhost/v1", model="qwen", temperature=0.2)
    llm = factory._build_llm(cfg)
    assert llm == "LLM"
    assert captured["api_key"] == "k"
    assert captured["base_url"] == "http://localhost/v1"
    assert captured["model"] == "qwen"
    assert captured["temperature"] == 0.2


def test_build_agent_wires_model_and_system_prompt(monkeypatch):
    calls = {}

    def fake_create_deep_agent(**kwargs):
        calls.update(kwargs)
        return "AGENT"

    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", fake_create_deep_agent)

    cfg = AgentConfig(api_key="k", base_url="b", model="m", system_prompt="SP")
    agent = factory.build_agent(cfg)

    assert agent == "AGENT"
    assert calls["model"] == "LLM"
    assert calls["system_prompt"] == "SP"


def test_build_agent_returns_native_object_with_invoke_and_stream():
    cfg = AgentConfig(api_key="dummy", base_url="http://localhost:9/v1", model="m")
    agent = factory.build_agent(cfg)
    assert agent is not None
    assert callable(getattr(agent, "invoke", None))
    assert callable(getattr(agent, "stream", None))


def test_build_agent_wires_hook_middleware_when_hooks_given(monkeypatch):
    calls = {}

    def fake_create_deep_agent(**kwargs):
        calls.update(kwargs)
        return "AGENT"

    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", fake_create_deep_agent)

    from agent_template.hooks import Hook
    cfg = AgentConfig(api_key="k", base_url="b", model="m")
    factory.build_agent(cfg, hooks=[Hook()])

    mw = calls["middleware"]
    assert len(mw) == 1
    from agent_template._middleware import HookMiddleware
    assert isinstance(mw[0], HookMiddleware)


def test_build_agent_no_hooks_passes_empty_middleware(monkeypatch):
    calls = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")

    cfg = AgentConfig(api_key="k", base_url="b", model="m")
    factory.build_agent(cfg)
    assert calls["middleware"] == []


def test_build_agent_passes_tools(monkeypatch):
    calls = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")
    cfg = AgentConfig(api_key="k", base_url="b", model="m")
    factory.build_agent(cfg, tools=["T1", "T2"])
    assert calls["tools"] == ["T1", "T2"]


def test_build_agent_defaults_tools_to_empty(monkeypatch):
    calls = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")
    factory.build_agent(AgentConfig(api_key="k", base_url="b", model="m"))
    assert calls["tools"] == []


def test_build_agent_appends_observability_middleware_when_enabled(monkeypatch):
    calls = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")

    from agent_template.observability import ObservabilityMiddleware
    from agent_template.hooks import Hook

    class _Obs:
        enabled = True
        instruments = {"tool_calls": None, "tool_duration": None, "llm_tokens": None, "agent_runs": None}
        logger = None

    cfg = AgentConfig(api_key="k", base_url="b", model="m")
    factory.build_agent(cfg, hooks=[Hook()], observability=_Obs())
    mw = calls["middleware"]
    assert any(isinstance(m, ObservabilityMiddleware) for m in mw)


def test_build_agent_no_observability_middleware_when_disabled(monkeypatch):
    calls = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")

    from agent_template.observability import ObservabilityMiddleware

    class _ObsOff:
        enabled = False
        instruments = {}
        logger = None

    factory.build_agent(AgentConfig(api_key="k", base_url="b", model="m"), observability=_ObsOff())
    assert not any(isinstance(m, ObservabilityMiddleware) for m in calls["middleware"])
