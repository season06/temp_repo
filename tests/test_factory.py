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
