import io
import zipfile

import httpx
import pytest

from agent_template.loaders import registry

REMOTE_CONFIG = """
agent:
  provider: deepagent
  model: remote-model
  system_prompt: "remote prompt"
mcp:
  - name: remote-mcp
    url: "https://mcp.internal/mcp"
skills:
"""


def make_zip(config_text=REMOTE_CONFIG, with_skill=True, extra=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("config.yaml", config_text)
        if with_skill:
            zf.writestr("skills/haiku/SKILL.md", "---\nname: haiku\ndescription: d\n---\nx")
        if extra:
            zf.writestr(extra, "evil")
    return buf.getvalue()


class FakeResponse:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("AGENT_REGISTRY_URL", "http://registry.internal")
    return tmp_path


def test_disabled_without_url(monkeypatch):
    monkeypatch.delenv("AGENT_REGISTRY_URL", raising=False)
    assert registry.fetch_remote("a") is None


def test_disabled_without_name(cache):
    assert registry.fetch_remote("") is None


def test_404_returns_none_without_warning(cache, monkeypatch, recwarn):
    monkeypatch.setattr(registry.httpx, "get", lambda *a, **kw: FakeResponse(404))
    assert registry.fetch_remote("ghost") is None
    assert len(recwarn) == 0  # 404 是正常流程


def test_connection_error_warns_and_falls_back(cache, monkeypatch):
    def boom(*a, **kw):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(registry.httpx, "get", boom)
    with pytest.warns(UserWarning, match="連線失敗"):
        assert registry.fetch_remote("a") is None


def test_500_warns_and_falls_back(cache, monkeypatch):
    monkeypatch.setattr(registry.httpx, "get", lambda *a, **kw: FakeResponse(500))
    with pytest.warns(UserWarning, match="500"):
        assert registry.fetch_remote("a") is None


def test_success_extracts_config_and_skills(cache, monkeypatch):
    called = {}

    def fake_get(url, timeout):
        called["url"] = url
        return FakeResponse(200, make_zip())

    monkeypatch.setattr(registry.httpx, "get", fake_get)
    bundle = registry.fetch_remote("my-agent")
    assert called["url"] == "http://registry.internal/agents/my-agent"
    assert bundle.config.agent.model == "remote-model"
    assert bundle.config.mcp[0].name == "remote-mcp"
    assert bundle.skills_dir.endswith("my-agent/skills")


def test_zip_without_skills_dir(cache, monkeypatch):
    monkeypatch.setattr(
        registry.httpx, "get", lambda *a, **kw: FakeResponse(200, make_zip(with_skill=False))
    )
    assert registry.fetch_remote("a").skills_dir is None


def test_bad_remote_config_warns_and_falls_back(cache, monkeypatch):
    bad = REMOTE_CONFIG.replace("system_prompt", "system_promt")
    monkeypatch.setattr(
        registry.httpx, "get", lambda *a, **kw: FakeResponse(200, make_zip(config_text=bad))
    )
    with pytest.warns(UserWarning, match="無法解析"):
        assert registry.fetch_remote("a") is None


def test_zip_slip_rejected(cache, monkeypatch):
    monkeypatch.setattr(
        registry.httpx, "get", lambda *a, **kw: FakeResponse(200, make_zip(extra="../evil.txt"))
    )
    with pytest.warns(UserWarning, match="無法解析"):
        assert registry.fetch_remote("a") is None


def test_refetch_clears_stale_cache(cache, monkeypatch):
    monkeypatch.setattr(registry.httpx, "get", lambda *a, **kw: FakeResponse(200, make_zip()))
    registry.fetch_remote("a")
    stale = registry._cache_root() / "a" / "stale.txt"
    stale.write_text("old", encoding="utf-8")
    registry.fetch_remote("a")
    assert not stale.exists()  # 拉新前先清舊


def test_remote_mcp_headers(monkeypatch):
    monkeypatch.setenv("AUTH_TOKEN", "tk-123")
    assert registry.remote_mcp_headers() == {"Authorization": "Bearer tk-123"}
    monkeypatch.setenv("AUTH_TOKEN", "")
    assert registry.remote_mcp_headers() is None
