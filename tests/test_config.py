import os

import pytest

from agent_template.config import ConfigError, load_config

VALID = """
agent:
  provider: deepagent
  model: qwen-max
  system_prompt: "you are a helpful agent"
local_tools:
  - "./tools/"
local_skills:
  - "./skills/"
"""


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_load_valid_config(tmp_path):
    config = load_config(write(tmp_path, "config.yaml", VALID))
    assert config.agent.provider == "deepagent"
    assert config.agent.model == "qwen-max"
    assert config.local_mcp == []


def test_relative_paths_resolve_to_config_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path.parent)  # cwd 故意不等於 config 目錄
    config = load_config(write(tmp_path, "config.yaml", VALID))
    assert config.local_tools == [str(tmp_path / "tools")]
    assert config.local_skills == [str(tmp_path / "skills")]


def test_agent_name_field(tmp_path):
    text = VALID.replace("agent:", "agent:\n  name: my-agent")
    config = load_config(write(tmp_path, "config.yaml", text))
    assert config.agent.name == "my-agent"


def test_local_a2a_field(tmp_path):
    text = VALID + '\nlocal_a2a:\n  - name: research\n    url: "http://other:9000"\n'
    config = load_config(write(tmp_path, "config.yaml", text))
    assert config.local_a2a[0].name == "research"


def test_agent_card_defaults_to_sibling_file(tmp_path):
    (tmp_path / "agent_card.yaml").write_text("name: x", encoding="utf-8")
    config = load_config(write(tmp_path, "config.yaml", VALID))
    assert config.agent_card == str(tmp_path / "agent_card.yaml")


def test_agent_card_declared_path_wins(tmp_path):
    (tmp_path / "cards").mkdir()
    (tmp_path / "cards" / "c.yaml").write_text("name: x", encoding="utf-8")
    text = VALID + '\nagent_card: "./cards/c.yaml"\n'
    config = load_config(write(tmp_path, "config.yaml", text))
    assert config.agent_card == str(tmp_path / "cards" / "c.yaml")


def test_agent_card_empty_when_no_file(tmp_path):
    config = load_config(write(tmp_path, "config.yaml", VALID))
    assert config.agent_card == ""


def test_unknown_field_fails_with_suggestion(tmp_path):
    bad = VALID.replace("system_prompt", "system_promt")
    with pytest.raises(ConfigError, match="system_prompt"):
        load_config(write(tmp_path, "config.yaml", bad))


def test_missing_file():
    with pytest.raises(ConfigError, match="找不到"):
        load_config("no/such/config.yaml")


def test_mcp_server_fields(tmp_path):
    text = VALID + '\nlocal_mcp:\n  - name: wiki\n    url: "http://x/mcp"\n'
    config = load_config(write(tmp_path, "config.yaml", text))
    assert config.local_mcp[0].name == "wiki"
    assert config.local_mcp[0].transport == "streamable-http"


def test_env_loaded_without_override(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "from-real-env")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    write(tmp_path, ".env", "LLM_API_KEY=from-file\nLLM_BASE_URL=http://file\n")
    load_config(write(tmp_path, "config.yaml", VALID))
    assert os.environ["LLM_API_KEY"] == "from-real-env"  # 不覆蓋既有環境變數
    assert os.environ["LLM_BASE_URL"] == "http://file"  # 空缺的才從 .env 補
    os.environ.pop("LLM_BASE_URL", None)  # dotenv 寫入的不在 monkeypatch 管轄,手動清
