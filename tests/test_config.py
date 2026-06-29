import dataclasses
import pytest
from agent_template.config import AgentConfig
from agent_template.errors import ConfigError

def _valid():
    return AgentConfig(model="qwen-max", base_url="https://x/v1", api_key="k")

def test_defaults():
    c = _valid()
    assert c.temperature == 0.0
    assert c.max_tokens is None
    assert c.max_retries == 2
    assert c.enable_audit_log is True

def test_frozen():
    c = _valid()
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.model = "other"

def test_rejects_empty_model():
    with pytest.raises(ConfigError):
        AgentConfig(model="", base_url="https://x/v1", api_key="k")

def test_rejects_bad_temperature():
    with pytest.raises(ConfigError):
        AgentConfig(model="m", base_url="https://x/v1", api_key="k", temperature=-1.0)
