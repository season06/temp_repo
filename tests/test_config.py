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


from agent_template.config import Config


def test_config_defaults():
    cfg = Config()
    assert cfg.auth_endpoint is None
    assert cfg.otel_endpoint is None
    assert cfg.sampling_ratio == 1.0
    assert cfg.o11y_enabled is True
    assert cfg.cid is None
    assert cfg.agent_version is None


def test_config_from_env_reads_values(monkeypatch):
    monkeypatch.setenv("AGENT_AUTH_ENDPOINT", "http://auth/verify")
    monkeypatch.setenv("AGENT_OTEL_ENDPOINT", "http://collector:4317")
    monkeypatch.setenv("AGENT_OTEL_SAMPLING_RATIO", "0.5")
    monkeypatch.setenv("AGENT_O11Y_ENABLED", "false")
    monkeypatch.setenv("AGENT_CID", "proj-123")
    monkeypatch.setenv("AGENT_VERSION", "1.2.3")
    cfg = Config.from_env()
    assert cfg.auth_endpoint == "http://auth/verify"
    assert cfg.otel_endpoint == "http://collector:4317"
    assert cfg.sampling_ratio == 0.5
    assert cfg.o11y_enabled is False
    assert cfg.cid == "proj-123"
    assert cfg.agent_version == "1.2.3"


def test_config_from_env_uses_defaults_when_unset(monkeypatch):
    for key in ("AGENT_AUTH_ENDPOINT", "AGENT_OTEL_ENDPOINT", "AGENT_OTEL_SAMPLING_RATIO",
                "AGENT_O11Y_ENABLED", "AGENT_CID", "AGENT_VERSION"):
        monkeypatch.delenv(key, raising=False)
    cfg = Config.from_env()
    assert cfg.auth_endpoint is None
    assert cfg.sampling_ratio == 1.0
    assert cfg.o11y_enabled is True
