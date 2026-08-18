import pytest
from deepagents.backends import FilesystemBackend, StateBackend

from agent_template.core import factory
from agent_template.config import Config, ConfigError


class FakeChat:
    def __init__(self, model=None, api_key=None, base_url=None):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url


def make_config(**agent_fields):
    return Config.model_validate({"agent": {"model": "qwen-max", **agent_fields}})


def test_build_model_reads_config_and_env(monkeypatch):
    monkeypatch.setattr(factory, "ChatOpenAI", FakeChat)
    monkeypatch.setenv("LLM_API_KEY", "key-123")
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.internal/v1")
    model = factory.build_model(make_config())
    assert (model.model, model.api_key, model.base_url) == (
        "qwen-max", "key-123", "http://llm.internal/v1"
    )


def test_build_model_missing_model_name(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_BASE_URL", "u")
    with pytest.raises(ConfigError, match="model"):
        factory.build_model(Config())


def test_build_model_missing_env(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    with pytest.raises(ConfigError, match="LLM_API_KEY"):
        factory.build_model(make_config())


def test_build_deepagent_passes_everything_through(monkeypatch):
    captured = {}
    monkeypatch.setattr(factory, "create_deep_agent", lambda **kw: captured.update(kw) or "native")
    model = object()
    result = factory.build_deepagent(
        make_config(), model, "be nice", ["tool"], ["/sk/a"], ["mw"], {"subagents": ["sub"]}
    )
    assert result == "native"
    assert isinstance(captured.pop("backend"), FilesystemBackend)
    assert captured == {
        "model": model,
        "system_prompt": "be nice",
        "tools": ["tool"],
        "skills": ["/sk/a"],
        "middleware": ["mw"],
        "subagents": ["sub"],
    }


def test_build_deepagent_builds_model_when_none(monkeypatch):
    captured = {}
    monkeypatch.setattr(factory, "create_deep_agent", lambda **kw: captured.update(kw) or "native")
    monkeypatch.setattr(factory, "ChatOpenAI", FakeChat)
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_BASE_URL", "u")
    factory.build_deepagent(make_config(), None, "", [], [], [], {})
    assert isinstance(captured["model"], FakeChat)
    assert "system_prompt" not in captured  # 空 prompt 不傳,交給 deepagents 預設


def test_backend_defaults_to_project_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    backend = factory.resolve_backend({})
    assert backend.cwd == tmp_path
    assert backend.virtual_mode is True
    assert backend.max_file_size_bytes == 10 * 1024 * 1024


def test_backend_keeps_user_params_but_forces_virtual_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    given = FilesystemBackend(root_dir="workspace", virtual_mode=False, max_file_size_mb=20)
    backend = factory.resolve_backend({"backend": given})
    assert backend.cwd == workspace
    assert backend.max_file_size_bytes == 20 * 1024 * 1024
    assert backend.virtual_mode is True


def test_backend_rejects_root_dir_outside_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    outside = FilesystemBackend(root_dir="/etc", virtual_mode=True)
    with pytest.raises(ConfigError, match="root_dir"):
        factory.resolve_backend({"backend": outside})


def test_backend_other_types_pass_through():
    given = StateBackend()
    assert factory.resolve_backend({"backend": given}) is given


def test_get_provider_builder():
    assert factory.get_provider_builder("deepagent") is factory.build_deepagent
    with pytest.raises(ConfigError, match="claude-sdk"):
        factory.get_provider_builder("claude-sdk")
