import os
import sys

import agent_template.core.builder as bmod
import agent_template.core.factory as factory
from agent_template.core import AgentBuilder
from agent_template.config import Config, LLMConfig, AgentSettings, SkillsConfig, McpsConfig, LocalSkill, LocalMcp
from agent_template.hooks import Hook

SKILL_FIXTURE = os.path.join(os.path.dirname(__file__), "skill_fixture.py")
MCP_SERVER = os.path.join(os.path.dirname(__file__), "mcp_server.py")


def _cfg(skills=None, mcps=None):
    return Config(
        llm=LLMConfig(api_key="k", base_url="b", model="m"),
        agent=AgentSettings(system_prompt="x"),
        skills=SkillsConfig(local=skills or []),
        mcps=McpsConfig(local=mcps or []),
    )


def test_add_methods_chain_and_accumulate():
    b = AgentBuilder(_cfg())
    r = (b.add_mcp("s1", "stdio", "./a.py")
          .add_skill("greet", SKILL_FIXTURE)
          .add_hook(Hook()))
    assert r is b
    assert b._mcps == [LocalMcp(name="s1", transport="stdio", path="./a.py", func=[])]
    assert b._skills == [LocalSkill(name="greet", path=SKILL_FIXTURE)]
    assert len(b._hooks) == 1


def test_builder_seeds_from_config_then_appends():
    cfg = _cfg(
        skills=[LocalSkill(name="from_cfg", path="./s.py")],
        mcps=[LocalMcp(name="cfg_mcp", transport="stdio", path="./m.py")],
    )
    b = AgentBuilder(cfg)
    # 起始清單來自 config
    assert [s.name for s in b._skills] == ["from_cfg"]
    assert [m.name for m in b._mcps] == ["cfg_mcp"]
    # add_* 追加在 config 之後
    b.add_skill("added", "./s2.py").add_mcp("added_mcp", "stdio", "./m2.py")
    assert [s.name for s in b._skills] == ["from_cfg", "added"]
    assert [m.name for m in b._mcps] == ["cfg_mcp", "added_mcp"]
    # 不汙染 config 本身
    assert [s.name for s in cfg.skills.local] == ["from_cfg"]
    assert [m.name for m in cfg.mcps.local] == ["cfg_mcp"]


def test_build_combines_mcp_and_skill_tools(monkeypatch):
    monkeypatch.setattr(bmod, "load_configured_mcp_tools", lambda mcps: ["MCP:" + m.name for m in mcps])
    monkeypatch.setattr(bmod, "load_skill_tools", lambda skills: ["SKILL:" + s.name for s in skills])
    captured = {}
    monkeypatch.setattr(bmod, "get_provider_builder",
                        lambda config, hooks, tools, observability=None: captured.update(tools=tools) or "AGENT")
    b = AgentBuilder(_cfg())
    agent = b.add_mcp("s1", "stdio", "./a.py").add_skill("greet", "./g.py").build()
    assert agent == "AGENT"
    assert captured["tools"] == ["MCP:s1", "SKILL:greet"]


def test_build_wires_real_mcp_and_skill_tools_into_create_deep_agent(monkeypatch):
    captured = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: captured.update(k) or "AGENT")
    b = AgentBuilder(_cfg())
    b.add_mcp("test", "stdio", MCP_SERVER).add_skill("greet", SKILL_FIXTURE)
    agent = b.build()
    assert agent == "AGENT"
    names = [getattr(t, "name", None) for t in captured["tools"]]
    assert "echo" in names   # real MCP tool loaded from the subprocess server
    assert "greet" in names  # skill tool loaded from the fixture file


def test_config_mcps_and_skills_are_loaded_at_build(monkeypatch):
    captured = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: captured.update(k) or "AGENT")
    cfg = _cfg(
        skills=[LocalSkill(name="greet", path=SKILL_FIXTURE)],
        mcps=[LocalMcp(name="test", transport="stdio", path=MCP_SERVER)],
    )
    AgentBuilder(cfg).build()
    names = [getattr(t, "name", None) for t in captured["tools"]]
    assert "echo" in names and "greet" in names  # both came straight from config


def test_add_mcp_func_filter(monkeypatch):
    captured = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: captured.update(k) or "AGENT")
    b = AgentBuilder(_cfg())
    # server exposes "echo"; ask for a non-existent func -> filtered out
    b.add_mcp("test", "stdio", MCP_SERVER, func=["nonexistent"])
    b.build()
    names = [getattr(t, "name", None) for t in captured["tools"]]
    assert "echo" not in names


def test_builder_passes_observability_to_build_agent(monkeypatch):
    captured = {}
    monkeypatch.setattr(bmod, "load_configured_mcp_tools", lambda mcps: [])
    monkeypatch.setattr(bmod, "load_skill_tools", lambda skills: [])
    monkeypatch.setattr(bmod, "get_provider_builder",
                        lambda config, hooks, tools, observability=None: captured.update(obs=observability) or "AGENT")

    class _Obs:
        enabled = True
        instruments = {}
        logger = None

    obs = _Obs()
    AgentBuilder(_cfg(), observability=obs).build()
    assert captured["obs"] is obs


def test_build_delegates_to_build_agent_with_full_config(monkeypatch):
    monkeypatch.setattr(bmod, "load_configured_mcp_tools", lambda mcps: [])
    monkeypatch.setattr(bmod, "load_skill_tools", lambda skills: [])
    seen = {}
    monkeypatch.setattr(bmod, "get_provider_builder",
                        lambda config, hooks, tools, observability=None: seen.update(provider=config.agent.provider) or "AGENT")
    cfg = _cfg()
    cfg.agent.provider = "my-framework"
    AgentBuilder(cfg).build()
    # build 委派給單一分派點 get_provider_builder,由它依 config.agent.provider 選具體 builder
    assert seen["provider"] == "my-framework"


def test_build_unknown_provider_raises():
    import pytest
    cfg = _cfg()
    cfg.agent.provider = "nope"
    with pytest.raises(ValueError, match="unsupported provider"):
        AgentBuilder(cfg).build()


