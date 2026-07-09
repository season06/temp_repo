from agent_template.core import factory
from agent_template.config import Config, LLMConfig, AgentSettings


def _cfg(system_prompt=None, **llm):
    return Config(llm=LLMConfig(**llm), agent=AgentSettings(system_prompt=system_prompt))


def test_build_llm_passes_openai_compatible_params(monkeypatch):
    captured = {}

    def fake_chat(**kwargs):
        captured.update(kwargs)
        return "LLM"

    monkeypatch.setattr(factory, "ChatOpenAI", fake_chat)
    cfg = _cfg(api_key="k", base_url="http://localhost/v1", model="qwen", temperature=0.2)
    llm = factory._build_llm(cfg.llm)
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

    cfg = _cfg(system_prompt="SP", api_key="k", base_url="b", model="m")
    agent = factory.get_provider_builder(cfg)

    assert agent == "AGENT"
    assert calls["model"] == "LLM"
    assert calls["system_prompt"] == "SP"


def test_build_agent_returns_native_object_with_invoke_and_stream():
    cfg = _cfg(api_key="dummy", base_url="http://localhost:9/v1", model="m")
    agent = factory.get_provider_builder(cfg)
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
    factory.get_provider_builder(_cfg(api_key="k", base_url="b", model="m"), hooks=[Hook()])

    mw = calls["middleware"]
    assert len(mw) == 1
    from agent_template.hooks import HookMiddleware
    assert isinstance(mw[0], HookMiddleware)


def test_build_agent_no_hooks_passes_empty_middleware(monkeypatch):
    calls = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")

    factory.get_provider_builder(_cfg(api_key="k", base_url="b", model="m"))
    assert calls["middleware"] == []


def test_build_agent_passes_tools(monkeypatch):
    calls = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")
    factory.get_provider_builder(_cfg(api_key="k", base_url="b", model="m"), tools=["T1", "T2"])
    assert calls["tools"] == ["T1", "T2"]


def test_build_agent_defaults_tools_to_empty(monkeypatch):
    calls = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")
    factory.get_provider_builder(_cfg(api_key="k", base_url="b", model="m"))
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

    factory.get_provider_builder(_cfg(api_key="k", base_url="b", model="m"), hooks=[Hook()], observability=_Obs())
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

    factory.get_provider_builder(_cfg(api_key="k", base_url="b", model="m"), observability=_ObsOff())
    assert not any(isinstance(m, ObservabilityMiddleware) for m in calls["middleware"])


def test_build_agent_builds_llm_from_config(monkeypatch):
    calls = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")
    factory.get_provider_builder(_cfg(api_key="k", base_url="b", model="m"))
    assert calls["model"] == "LLM"


def test_default_provider_is_deepagent():
    assert factory._PROVIDER_BUILDERS["deepagent"] is factory.build_deepagent


def test_get_provider_builder_unknown_raises():
    import pytest
    cfg = _cfg(api_key="k", base_url="b", model="m")
    cfg.agent.provider = "nope"
    with pytest.raises(ValueError, match="unsupported provider"):
        factory.get_provider_builder(cfg)


def test_build_agent_dispatches_to_registered_provider(monkeypatch):
    captured = {}
    monkeypatch.setitem(factory._PROVIDER_BUILDERS, "custom",
                        lambda config, hooks, tools, observability=None: captured.update(hit=True) or "CUSTOM")
    cfg = _cfg(api_key="k", base_url="b", model="m")
    cfg.agent.provider = "custom"
    assert factory.get_provider_builder(cfg) == "CUSTOM"
    assert captured["hit"] is True
