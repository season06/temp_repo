import pytest

from agent_template.a2a.card import CardSpec, load_card_file, resolve_card
from agent_template.config import ConfigError

CARD_YAML = """
name: my-agent
description: a helpful agent
version: "1.2.0"
"""


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_load_yaml_card(tmp_path):
    card = load_card_file(write(tmp_path, "agent_card.yaml", CARD_YAML))
    assert card.name == "my-agent"
    assert card.version == "1.2.0"
    assert card.url == ""
    assert card.skills == []


def test_load_json_card(tmp_path):
    card = load_card_file(
        write(tmp_path, "agent_card.json", '{"name": "j-agent", "skills": [{"id": "s", "name": "S"}]}')
    )
    assert card.name == "j-agent"
    assert card.skills[0].id == "s"


def test_missing_name_fails(tmp_path):
    with pytest.raises(ConfigError, match="agent card"):
        load_card_file(write(tmp_path, "agent_card.yaml", "description: no name"))


def test_missing_file_fails(tmp_path):
    with pytest.raises(ConfigError, match="找不到"):
        load_card_file(str(tmp_path / "nope.yaml"))


def test_resolve_remote_wins(tmp_path):
    local = write(tmp_path, "local.yaml", CARD_YAML)
    remote = write(tmp_path, "remote.yaml", "name: remote-agent")
    assert resolve_card(local, remote).name == "remote-agent"


def test_resolve_bad_remote_falls_back_to_local(tmp_path):
    local = write(tmp_path, "local.yaml", CARD_YAML)
    remote = write(tmp_path, "remote.yaml", "unknown_field: x")
    with pytest.warns(UserWarning, match="remote agent card"):
        assert resolve_card(local, remote).name == "my-agent"


def test_resolve_bad_local_fails_fast(tmp_path):
    local = write(tmp_path, "local.yaml", "unknown_field: x")
    with pytest.raises(ConfigError):
        resolve_card(local, None)


def test_resolve_neither_returns_none():
    assert resolve_card("", None) is None
