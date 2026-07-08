from agent_template.config import AgentConfig


def test_agent_config_holds_required_fields():
    cfg = AgentConfig(api_key="k", base_url="http://localhost/v1", model="qwen")
    assert cfg.api_key == "k"
    assert cfg.base_url == "http://localhost/v1"
    assert cfg.model == "qwen"


def test_agent_config_defaults():
    cfg = AgentConfig(api_key="k", base_url="b", model="m")
    assert cfg.temperature == 0.0
    assert cfg.system_prompt is None


def test_agent_config_overrides():
    cfg = AgentConfig(api_key="k", base_url="b", model="m", temperature=0.3, system_prompt="SP")
    assert cfg.temperature == 0.3
    assert cfg.system_prompt == "SP"
