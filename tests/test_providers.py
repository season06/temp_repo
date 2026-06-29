import pytest
import agent_template.providers as providers
from agent_template.config import AgentConfig
from agent_template.errors import ProviderError


class FakeChatModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_build_chat_model_passes_config(monkeypatch):
    monkeypatch.setattr(providers, "ChatOpenAI", FakeChatModel)
    cfg = AgentConfig(model="qwen-max", base_url="https://x/v1", api_key="k",
                      temperature=0.2, max_retries=3)
    model = providers.build_chat_model(cfg)
    assert model.kwargs["model"] == "qwen-max"
    assert model.kwargs["base_url"] == "https://x/v1"
    assert model.kwargs["api_key"] == "k"
    assert model.kwargs["temperature"] == 0.2
    assert model.kwargs["max_retries"] == 3
    assert model.kwargs["max_tokens"] is None
    assert model.kwargs["timeout"] == 60.0


def test_build_chat_model_wraps_errors(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("init failed")
    monkeypatch.setattr(providers, "ChatOpenAI", boom)
    cfg = AgentConfig(model="m", base_url="https://x/v1", api_key="k")
    with pytest.raises(ProviderError):
        providers.build_chat_model(cfg)


def test_build_chat_model_chains_cause(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("init failed")
    monkeypatch.setattr(providers, "ChatOpenAI", boom)
    cfg = AgentConfig(model="m", base_url="https://x/v1", api_key="k")
    with pytest.raises(ProviderError) as excinfo:
        providers.build_chat_model(cfg)
    assert isinstance(excinfo.value.__cause__, RuntimeError)
