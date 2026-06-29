import pytest
import agent_template.factory as factory
from agent_template.config import AgentConfig
from agent_template.errors import ConfigError


@pytest.fixture
def patched(monkeypatch):
    captured = {}

    def fake_build_chat_model(config):
        captured["model_built"] = True
        return "FAKE_MODEL"

    def fake_create_deep_agent(model, tools, system_prompt):
        captured["tools"] = tools
        captured["system_prompt"] = system_prompt
        captured["model"] = model
        return "FAKE_AGENT"

    monkeypatch.setattr(factory, "build_chat_model", fake_build_chat_model)
    monkeypatch.setattr(factory, "create_deep_agent", fake_create_deep_agent)
    return captured


def _cfg():
    return AgentConfig(model="qwen-max", base_url="https://x/v1", api_key="k")


def test_requires_config():
    with pytest.raises(ConfigError):
        factory.build_agent("do the task", config=None)


def test_builds_agent_with_task_prompt(patched):
    agent = factory.build_agent("do the task", tools=["t1"], config=_cfg())
    assert agent == "FAKE_AGENT"
    assert patched["system_prompt"] == "do the task"   # P1: 未包外殼
    assert patched["tools"] == ["t1"]
    assert patched["model"] == "FAKE_MODEL"


def test_tools_default_empty(patched):
    factory.build_agent("task", config=_cfg())
    assert patched["tools"] == []
