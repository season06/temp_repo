import pytest
from langchain_core.tools import tool

from agent_template import AgentBuilder
from agent_template.config import ConfigError
from agent_template.core import factory
from agent_template.core.agent import Agent

CONFIG = """
agent:
  provider: deepagent
  model: qwen-max
  system_prompt: "base prompt"
local_tools:
  - "./tools/"
local_skills:
  - "./skills/"
"""

TOOL_FILE = '''
from langchain_core.tools import tool

@tool
def add(a: int, b: int) -> int:
    """兩數相加。"""
    return a + b
'''


@tool
def add(a: int, b: int) -> int:
    """撞名用:與 config 的 add 同名。"""
    return 0


@tool
def extra(text: str) -> str:
    """不撞名的 build() tool。"""
    return text


@pytest.fixture
def project(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "math.py").write_text(TOOL_FILE, encoding="utf-8")
    skill = tmp_path / "skills" / "haiku"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: haiku\ndescription: d\n---\nbody", encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    return config


@pytest.fixture
def captured(monkeypatch):
    box = {}

    def fake_create(**kw):
        box.update(kw)
        return "native-agent"

    monkeypatch.setattr(factory, "create_deep_agent", fake_create)
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **kw: ("chat", kw))
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_BASE_URL", "u")
    monkeypatch.delenv("AGENT_REGISTRY_URL", raising=False)  # 保險:不受外部環境影響
    return box


def test_only_accepts_path():
    with pytest.raises(TypeError, match="路徑"):
        AgentBuilder({"agent": {}})


def test_build_wires_config_sources(project, captured):
    agent = AgentBuilder(project).build()
    assert isinstance(agent, Agent)
    assert agent.native == "native-agent"
    assert [t.name for t in captured["tools"]] == ["add"]
    assert captured["skills"] == [str(project.parent / "skills" / "haiku")]
    assert captured["system_prompt"] == "base prompt"
    assert captured["model"][0] == "chat"
    assert captured["model"][1]["model"] == "qwen-max"


def test_model_conflict_config_wins(project, captured):
    with pytest.warns(UserWarning, match="model.*config 為主"):
        AgentBuilder(project).build(model=object())
    assert captured["model"][0] == "chat"  # 仍由 config 建


def test_system_prompt_conflict_config_wins(project, captured):
    with pytest.warns(UserWarning, match="system_prompt.*config 為主"):
        AgentBuilder(project).build(system_prompt="override attempt")
    assert captured["system_prompt"] == "base prompt"


def test_tools_merge_and_name_collision(project, captured):
    with pytest.warns(UserWarning, match='tool "add".*撞名'):
        AgentBuilder(project).build(tools=[add, extra])
    names = [t.name for t in captured["tools"]]
    assert names == ["add", "extra"]  # config 的 add 留下,build 的 add 丟棄
    assert captured["tools"][0].invoke({"a": 1, "b": 2}) == 3  # 是 config 那份


def test_skills_merge_and_name_collision(project, captured, tmp_path):
    other = tmp_path / "elsewhere" / "haiku"
    other.mkdir(parents=True)
    (other / "SKILL.md").write_text("---\nname: haiku\ndescription: d\n---\nx", encoding="utf-8")
    fresh = tmp_path / "elsewhere" / "fresh"
    fresh.mkdir()
    (fresh / "SKILL.md").write_text("---\nname: fresh\ndescription: d\n---\nx", encoding="utf-8")
    with pytest.warns(UserWarning, match='skill "haiku".*撞名'):
        AgentBuilder(project).build(skills=[str(other), str(fresh)])
    assert captured["skills"] == [
        str(project.parent / "skills" / "haiku"),
        str(fresh),
    ]


def test_middleware_merges_sdk_before_user(project, captured, monkeypatch):
    from agent_template.core import builder

    sdk_mw, user_mw = object(), object()
    monkeypatch.setattr(builder, "_SDK_MIDDLEWARE", [sdk_mw])
    AgentBuilder(project).build(middleware=[user_mw])
    assert captured["middleware"] == [sdk_mw, user_mw]  # SDK 在前,使用者在後


def test_middleware_sdk_only_when_user_gives_none(project, captured, monkeypatch):
    from agent_template.core import builder

    sdk_mw = object()
    monkeypatch.setattr(builder, "_SDK_MIDDLEWARE", [sdk_mw])
    AgentBuilder(project).build()
    assert captured["middleware"] == [sdk_mw]


def test_native_kwargs_passthrough(project, captured):
    AgentBuilder(project).build(subagents=["sub"])
    assert captured["subagents"] == ["sub"]


def test_unknown_provider(project, captured):
    bad = project.parent / "bad.yaml"
    bad.write_text(CONFIG.replace("deepagent", "unknown-provider"), encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown-provider"):
        AgentBuilder(bad).build()


# ---- Agent Registry (P6) ----

from agent_template.loaders.registry import RemoteBundle, RemoteConfig


def make_bundle(tmp_path, mcp=None, with_skill_named=None):
    remote = RemoteConfig.model_validate({
        "agent": {"provider": "deepagent", "model": "remote-model",
                  "system_prompt": "remote prompt"},
        "mcp": mcp or [],
    })
    skills_dir = None
    if with_skill_named:
        d = tmp_path / "remote_skills" / with_skill_named
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("---\nname: r\ndescription: d\n---\nx", encoding="utf-8")
        skills_dir = str(tmp_path / "remote_skills")
    return RemoteBundle(remote, skills_dir)


def test_remote_agent_section_wins_but_name_stays_local(project, captured, monkeypatch, tmp_path):
    from agent_template.core import builder

    named = CONFIG.replace("agent:", "agent:\n  name: my-agent")
    project.write_text(named, encoding="utf-8")
    seen = {}

    def fake_fetch(name):
        seen["name"] = name
        return make_bundle(tmp_path)

    monkeypatch.setattr(builder, "fetch_remote", fake_fetch)
    AgentBuilder(project).build()
    assert seen["name"] == "my-agent"  # 用 local 的 name 查詢
    assert captured["system_prompt"] == "remote prompt"
    assert captured["model"][1]["model"] == "remote-model"


def test_remote_skill_beats_local_on_collision(project, captured, monkeypatch, tmp_path):
    from agent_template.core import builder

    bundle = make_bundle(tmp_path, with_skill_named="haiku")  # local 也有 haiku
    monkeypatch.setattr(builder, "fetch_remote", lambda name: bundle)
    with pytest.warns(UserWarning, match="haiku"):
        AgentBuilder(project).build()
    assert captured["skills"] == [str(tmp_path / "remote_skills" / "haiku")]


def test_remote_mcp_gets_bearer_and_missing_token_warns(project, captured, monkeypatch, tmp_path):
    from agent_template.core import builder

    seen = {}

    def fake_load(servers, headers=None):
        if servers and servers[0].name == "remote-mcp":
            seen["headers"] = headers
        return []

    monkeypatch.setattr(builder, "load_mcp_tools", fake_load)
    bundle = make_bundle(tmp_path, mcp=[{"name": "remote-mcp", "url": "https://m/mcp"}])
    monkeypatch.setattr(builder, "fetch_remote", lambda name: bundle)

    monkeypatch.setenv("AUTH_TOKEN", "tk")
    AgentBuilder(project).build()
    assert seen["headers"] == {"Authorization": "Bearer tk"}

    monkeypatch.setenv("AUTH_TOKEN", "")
    with pytest.warns(UserWarning, match="AUTH_TOKEN"):
        AgentBuilder(project).build()


def test_no_remote_keeps_local_behavior(project, captured, monkeypatch):
    from agent_template.core import builder

    monkeypatch.setattr(builder, "fetch_remote", lambda name: None)
    AgentBuilder(project).build()
    assert captured["system_prompt"] == "base prompt"
