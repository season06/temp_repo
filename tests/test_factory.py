import pytest
import agent_template.factory as factory
from agent_template.config import AgentConfig
from agent_template.errors import ConfigError
from agent_template._secure._guard import InputGuardMiddleware
from agent_template._secure._validation import OutputValidationMiddleware
from agent_template._secure._envelope import SAFETY_PREFIX, SAFETY_SUFFIX


@pytest.fixture
def patched(monkeypatch):
    captured = {}

    def fake_build_chat_model(config):
        return "FAKE_MODEL"

    def fake_create_deep_agent(model, tools, system_prompt, middleware):
        captured["model"] = model
        captured["tools"] = tools
        captured["system_prompt"] = system_prompt
        captured["middleware"] = middleware
        return "FAKE_AGENT"

    monkeypatch.setattr(factory, "build_chat_model", fake_build_chat_model)
    monkeypatch.setattr(factory, "create_deep_agent", fake_create_deep_agent)
    return captured


def _cfg():
    return AgentConfig(model="qwen-max", base_url="https://x/v1", api_key="k")


def test_requires_config():
    with pytest.raises(ConfigError):
        factory.build_agent("do the task", config=None)


def test_system_prompt_is_sandwiched(patched):
    factory.build_agent("do the task", config=_cfg())
    sp = patched["system_prompt"]
    assert sp.startswith(SAFETY_PREFIX)
    assert sp.endswith(SAFETY_SUFFIX)
    assert "do the task" in sp


def test_security_middleware_always_present(patched):
    factory.build_agent("task", config=_cfg())
    mw = patched["middleware"]
    assert any(isinstance(m, InputGuardMiddleware) for m in mw)
    assert any(isinstance(m, OutputValidationMiddleware) for m in mw)


def test_no_param_can_disable_security(patched):
    # build_agent 不接受任何停用安全層的參數;傳未知參數應 TypeError
    with pytest.raises(TypeError):
        factory.build_agent("task", config=_cfg(), disable_security=True)


def test_tools_default_empty(patched):
    factory.build_agent("task", config=_cfg())
    assert patched["tools"] == []


def test_audit_called_when_enabled(monkeypatch, patched):
    calls = []
    monkeypatch.setattr(factory, "audit", lambda event: calls.append(event))
    factory.build_agent("task", config=_cfg())
    assert len(calls) == 1
    assert calls[0]["action"] == "build_agent"


def test_audit_suppressed_when_disabled(monkeypatch, patched):
    calls = []
    monkeypatch.setattr(factory, "audit", lambda event: calls.append(event))
    cfg = AgentConfig(model="qwen-max", base_url="https://x/v1", api_key="k", enable_audit_log=False)
    factory.build_agent("task", config=cfg)
    assert calls == []
