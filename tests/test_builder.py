import os
import sys

import agent_template.builder as bmod
import agent_template.factory as factory
from agent_template.builder import AgentBuilder
from agent_template.config import AgentConfig
from agent_template.hooks import Hook
from agent_template.skills import Skill, MockSkillRegistry


def _cfg():
    return AgentConfig(api_key="k", base_url="b", model="m")


def test_add_methods_chain_and_accumulate():
    b = AgentBuilder(_cfg())
    r = b.add_mcp("s1", {"transport": "stdio"}).add_skill("greet").add_hook(Hook())
    assert r is b
    assert b._mcp_connections == {"s1": {"transport": "stdio"}}
    assert b._skill_ids == ["greet"]
    assert len(b._hooks) == 1


def test_build_combines_mcp_and_skill_tools(monkeypatch):
    monkeypatch.setattr(bmod, "load_mcp_tools", lambda conns: ["MCP_TOOL"] if conns else [])
    captured = {}
    monkeypatch.setattr(bmod, "build_agent",
                        lambda config, hooks, tools, observability=None, model=None: captured.update(hooks=hooks, tools=tools) or "AGENT")
    reg = MockSkillRegistry({"greet": Skill("greet", "d", "hi")})
    b = AgentBuilder(_cfg(), skill_registry=reg)
    agent = b.add_mcp("s1", {"transport": "stdio"}).add_skill("greet").build()
    assert agent == "AGENT"
    tools = captured["tools"]
    assert "MCP_TOOL" in tools
    assert any(getattr(t, "name", None) == "greet" for t in tools)


def test_build_wires_real_mcp_and_skill_tools_into_create_deep_agent(monkeypatch):
    captured = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: captured.update(k) or "AGENT")
    server = os.path.join(os.path.dirname(__file__), "mcp_server.py")
    reg = MockSkillRegistry({"greet": Skill("greet", "d", "hi from skill")})
    b = AgentBuilder(_cfg(), skill_registry=reg)
    b.add_mcp("test", {"transport": "stdio", "command": sys.executable, "args": [server]}).add_skill("greet")
    agent = b.build()
    assert agent == "AGENT"
    names = [getattr(t, "name", None) for t in captured["tools"]]
    assert "echo" in names   # real MCP tool loaded from the subprocess server
    assert "greet" in names  # skill tool


def test_multi_mount_accumulates(monkeypatch):
    monkeypatch.setattr(bmod, "load_mcp_tools", lambda conns: [f"MCP:{name}" for name in conns])
    captured = {}
    monkeypatch.setattr(bmod, "build_agent",
                        lambda config, hooks, tools, observability=None, model=None: captured.update(tools=tools) or "AGENT")
    reg = MockSkillRegistry({"a": Skill("a", "d", "x"), "b": Skill("b", "d", "y")})
    b = AgentBuilder(_cfg(), skill_registry=reg)
    b.add_mcp("s1", {"transport": "stdio"}).add_mcp("s2", {"transport": "stdio"})
    b.add_skill("a").add_skill("b")
    b.build()
    tools = captured["tools"]
    assert "MCP:s1" in tools and "MCP:s2" in tools
    skill_names = [getattr(t, "name", None) for t in tools]
    assert skill_names.count("a") == 1 and skill_names.count("b") == 1


def test_add_mcp_same_name_overwrites():
    b = AgentBuilder(_cfg())
    b.add_mcp("s", {"transport": "stdio", "command": "a"}).add_mcp("s", {"transport": "stdio", "command": "b"})
    assert b._mcp_connections == {"s": {"transport": "stdio", "command": "b"}}


def test_builder_passes_observability_to_build_agent(monkeypatch):
    captured = {}
    monkeypatch.setattr(bmod, "load_mcp_tools", lambda conns: [])
    monkeypatch.setattr(bmod, "build_agent",
                        lambda config, hooks, tools, observability=None, model=None: captured.update(obs=observability) or "AGENT")

    class _Obs:
        enabled = True
        instruments = {}
        logger = None

    obs = _Obs()
    b = AgentBuilder(_cfg(), observability=obs)
    b.build()
    assert captured["obs"] is obs


def test_builder_passes_injected_model(monkeypatch):
    captured = {}
    monkeypatch.setattr(bmod, "load_mcp_tools", lambda conns: [])
    monkeypatch.setattr(bmod, "build_agent",
                        lambda config, hooks, tools, observability=None, model=None: captured.update(model=model) or "AGENT")
    AgentBuilder(_cfg(), model="FAKE").build()
    assert captured["model"] == "FAKE"
