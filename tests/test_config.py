import textwrap

import pytest

from agent_template.config import (
    AgentSettings,
    AuthConfig,
    Config,
    LLMConfig,
    LocalMcp,
    LocalSkill,
    McpsConfig,
    ObservabilityConfig,
    SkillsConfig,
)


# ---------------------------------------------------------------------------
# env-sourced sections
# ---------------------------------------------------------------------------


def test_llm_config_defaults():
    cfg = LLMConfig()
    assert cfg.api_key == ""
    assert cfg.base_url == ""
    assert cfg.model == ""
    assert cfg.temperature == 0.0


def test_llm_config_load_from_env():
    env = {"LLM_API_KEY": "k", "LLM_BASE_URL": "http://x/v1", "LLM_MODEL": "qwen", "LLM_TEMPERATURE": "0.3"}
    cfg = LLMConfig.load_from_env(env)
    assert cfg.api_key == "k"
    assert cfg.base_url == "http://x/v1"
    assert cfg.model == "qwen"
    assert cfg.temperature == 0.3


def test_observability_config_load_from_env():
    env = {"OTEL_ENABLED": "true", "OTEL_ENDPOINT": "http://c:4318", "OTEL_SAMPLING_RATIO": "0.5",
           "SERVICE_NAME": "svc", "CID": "proj-1", "AGENT_VERSION": "1.2.3"}
    cfg = ObservabilityConfig.load_from_env(env)
    assert cfg.enabled is True
    assert cfg.endpoint == "http://c:4318"
    assert cfg.sampling_ratio == 0.5
    assert cfg.service_name == "svc"
    assert cfg.cid == "proj-1"
    assert cfg.agent_version == "1.2.3"


def test_observability_defaults_disabled_when_unset():
    cfg = ObservabilityConfig.load_from_env({})
    assert cfg.enabled is False
    assert cfg.endpoint is None
    assert cfg.sampling_ratio == 1.0
    assert cfg.service_name == "agent_template"


@pytest.mark.parametrize("value", ["true", "True", "1", "yes", "ON"])
def test_observability_enabled_truthy(value):
    assert ObservabilityConfig.load_from_env({"OTEL_ENABLED": value}).enabled is True


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "anything"])
def test_observability_enabled_falsy(value):
    assert ObservabilityConfig.load_from_env({"OTEL_ENABLED": value}).enabled is False


def test_auth_config_load_from_env():
    assert AuthConfig.load_from_env({"AUTH_ENDPOINT": "http://auth/verify"}).endpoint == "http://auth/verify"
    assert AuthConfig.load_from_env({}).endpoint is None


# ---------------------------------------------------------------------------
# yaml-sourced sections
# ---------------------------------------------------------------------------


def test_agent_settings_load_from_yaml():
    cfg = AgentSettings.load_from_yaml({"agent": {"provider": "deepagent", "system_prompt": "SP"}})
    assert cfg.provider == "deepagent"
    assert cfg.system_prompt == "SP"


def test_agent_settings_defaults_when_missing():
    cfg = AgentSettings.load_from_yaml({})
    assert cfg.provider == "deepagent"
    assert cfg.system_prompt is None


def test_skills_config_load_from_yaml():
    data = {
        "skills__local": [{"name": "make_a_joke", "path": "./skills/make_a_joke.py"}],
        "skills__remote": {"registry_url": "http://reg", "name": ["a", "b"]},
    }
    cfg = SkillsConfig.load_from_yaml(data)
    assert cfg.local == [LocalSkill(name="make_a_joke", path="./skills/make_a_joke.py")]
    assert cfg.remote.registry_url == "http://reg"
    assert cfg.remote.name == ["a", "b"]


def test_mcps_config_load_from_yaml():
    data = {
        "mcps__local": [{"name": "test-func", "transport": "stdio", "path": "./mcp/s.py", "func": ["get"]}],
        "mcps__remote": {"registry_url": "", "name": []},
    }
    cfg = McpsConfig.load_from_yaml(data)
    assert cfg.local == [LocalMcp(name="test-func", transport="stdio", path="./mcp/s.py", func=["get"])]
    assert cfg.remote.registry_url == ""


def test_skills_and_mcps_default_empty_when_missing():
    assert SkillsConfig.load_from_yaml({}).local == []
    assert McpsConfig.load_from_yaml({}).local == []


# ---------------------------------------------------------------------------
# top-level Config loaders
# ---------------------------------------------------------------------------


def test_config_defaults():
    cfg = Config()
    assert cfg.llm.api_key == ""
    assert cfg.agent.provider == "deepagent"
    assert cfg.skills.local == []
    assert cfg.mcps.local == []
    assert cfg.observability.enabled is False
    assert cfg.auth.endpoint is None


def test_config_load_from_env_reads_only_env_sections(tmp_path, monkeypatch):
    for key in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "OTEL_ENABLED", "OTEL_ENDPOINT", "AUTH_ENDPOINT"):
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(textwrap.dedent("""
        LLM_API_KEY=k
        LLM_BASE_URL=http://x/v1
        LLM_MODEL=qwen
        OTEL_ENABLED=true
        OTEL_ENDPOINT=http://c:4318
        AUTH_ENDPOINT=http://auth/verify
    """))
    cfg = Config.load_from_env(env_file)
    assert cfg.llm.api_key == "k"
    assert cfg.llm.model == "qwen"
    assert cfg.observability.enabled is True
    assert cfg.auth.endpoint == "http://auth/verify"
    # yaml sections stay default
    assert cfg.skills.local == []


def test_config_load_from_yaml_reads_only_yaml_sections(tmp_path):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text(textwrap.dedent("""
        agent:
          provider: deepagent
          system_prompt: hi
        skills__local:
          - name: joke
            path: ./skills/joke.py
        mcps__local:
          - name: srv
            transport: stdio
            path: ./mcp/s.py
            func: ["get"]
    """))
    cfg = Config.load_from_yaml(yaml_file)
    assert cfg.agent.system_prompt == "hi"
    assert cfg.skills.local[0].name == "joke"
    assert cfg.mcps.local[0].transport == "stdio"
    # env sections stay default
    assert cfg.llm.api_key == ""


def test_config_load_merges_yaml_and_env(tmp_path, monkeypatch):
    for key in ("LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)
    (tmp_path / ".env").write_text("LLM_API_KEY=k\nLLM_MODEL=qwen\n")
    (tmp_path / "config.yaml").write_text("agent:\n  system_prompt: SP\n")
    cfg = Config.load(tmp_path / "config.yaml", tmp_path / ".env")
    assert cfg.llm.api_key == "k"
    assert cfg.agent.system_prompt == "SP"


def test_config_load_missing_files_returns_defaults(tmp_path, monkeypatch):
    for key in ("LLM_API_KEY", "LLM_MODEL", "OTEL_ENABLED", "AUTH_ENDPOINT"):
        monkeypatch.delenv(key, raising=False)
    cfg = Config.load(tmp_path / "nope.yaml", tmp_path / "nope.env")
    assert cfg.llm.api_key == ""
    assert cfg.agent.system_prompt is None


def test_real_env_overrides_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("LLM_API_KEY=from-file\n")
    monkeypatch.setenv("LLM_API_KEY", "from-real-env")
    cfg = Config.load_from_env(tmp_path / ".env")
    assert cfg.llm.api_key == "from-real-env"
