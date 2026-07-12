from agent_template.core import factory
from agent_template.config import Config, LLMConfig, AgentSettings


def _cfg(system_prompt=None, **llm):
    from agent_template.config import AuthConfig
    return Config(llm=LLMConfig(**llm), agent=AgentSettings(system_prompt=system_prompt),
                  auth=AuthConfig(endpoint="http://auth/verify"))


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
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")

    from agent_template.hooks import Hook, AuthMiddleware, HookMiddleware
    from agent_template.auth import AuthHook
    user = Hook()
    factory.get_provider_builder(_cfg(api_key="k", base_url="b", model="m"), hooks=[user])

    mw = calls["middleware"]
    assert isinstance(mw[0], AuthMiddleware)
    assert isinstance(mw[1], HookMiddleware)
    assert isinstance(mw[1]._hooks[0], AuthHook)   # auth 先
    assert mw[1]._hooks[1] is user                 # 使用者 hook 在後


def test_build_agent_no_hooks_still_has_auth_and_hook_middleware(monkeypatch):
    calls = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")
    factory.get_provider_builder(_cfg(api_key="k", base_url="b", model="m"))
    from agent_template.hooks import AuthMiddleware, HookMiddleware
    mw = calls["middleware"]
    assert isinstance(mw[0], AuthMiddleware)
    assert isinstance(mw[1], HookMiddleware)
    assert len(mw) == 2


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


def _cfg_auth(endpoint="http://auth/verify"):
    from agent_template.config import AuthConfig
    cfg = _cfg(api_key="k", base_url="b", model="m")
    cfg.auth = AuthConfig(endpoint=endpoint)
    return cfg


def test_assemble_middleware_auth_first_then_hookmiddleware():
    from agent_template.hooks import AuthMiddleware, HookMiddleware
    mw = factory.assemble_middleware(_cfg_auth())
    assert isinstance(mw[0], AuthMiddleware)
    assert isinstance(mw[1], HookMiddleware)
    assert len(mw) == 2


def test_assemble_middleware_injects_authhook_before_user_hooks():
    from agent_template.auth import AuthHook
    from agent_template.hooks import Hook
    user = Hook()
    mw = factory.assemble_middleware(_cfg_auth(), hooks=[user])
    hookmw_hooks = mw[1]._hooks
    assert isinstance(hookmw_hooks[0], AuthHook)   # auth 先
    assert hookmw_hooks[1] is user                 # 使用者 hook 疊加在後


def test_assemble_middleware_missing_endpoint_raises():
    import pytest
    from agent_template.config import AuthConfig
    cfg = _cfg(api_key="k", base_url="b", model="m")
    cfg.auth = AuthConfig()   # 無 endpoint → fail-closed
    with pytest.raises(ValueError, match="auth endpoint not configured"):
        factory.assemble_middleware(cfg)


def test_build_missing_auth_endpoint_raises(monkeypatch):
    import pytest
    from agent_template.config import AuthConfig
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: "AGENT")
    cfg = _cfg(api_key="k", base_url="b", model="m")
    cfg.auth = AuthConfig()   # 無 endpoint
    with pytest.raises(ValueError, match="auth endpoint not configured"):
        factory.get_provider_builder(cfg)


def test_build_passes_context_schema(monkeypatch):
    from agent_template.auth import AuthContext
    calls = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")
    factory.get_provider_builder(_cfg_auth())
    assert calls["context_schema"] is AuthContext
