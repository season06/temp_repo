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
