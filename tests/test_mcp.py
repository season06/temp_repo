import asyncio
import os
import sys

from agent_template.config import LocalMcp
from agent_template.tools import mcp as mcp_mod
from agent_template.tools import load_mcp_tools, load_configured_mcp_tools, mcp_to_connection


def test_empty_connections_returns_empty():
    assert load_mcp_tools({}) == []
    assert load_mcp_tools(None) == []


def test_load_returns_client_tools(monkeypatch):
    class FakeClient:
        def __init__(self, connections):
            self.connections = connections

        async def get_tools(self):
            return ["TOOL_A", "TOOL_B"]

    monkeypatch.setattr(mcp_mod, "MultiServerMCPClient", FakeClient)
    tools = load_mcp_tools({"s": {"transport": "stdio"}})
    assert tools == ["TOOL_A", "TOOL_B"]


def test_load_real_stdio_server():
    server = os.path.join(os.path.dirname(__file__), "mcp_server.py")
    tools = load_mcp_tools({
        "test": {"transport": "stdio", "command": sys.executable, "args": [server]}
    })
    names = [t.name for t in tools]
    assert "echo" in names
    echo = next(t for t in tools if t.name == "echo")
    # MCP tools are async-only; invoke via ainvoke
    result = asyncio.run(echo.ainvoke({"text": "hi"}))
    assert "echo:hi" in str(result)


def test_mcp_to_connection_translates_stdio_and_http():
    stdio = mcp_to_connection(LocalMcp(name="s", transport="stdio", path="./server.py"))
    assert stdio["transport"] == "stdio"
    assert stdio["command"] == sys.executable
    assert stdio["args"] == ["./server.py"]

    http = mcp_to_connection(LocalMcp(name="s", transport="streamable_http", path="http://h/mcp"))
    assert http == {"transport": "streamable_http", "url": "http://h/mcp"}


def test_load_configured_filters_by_func():
    server = os.path.join(os.path.dirname(__file__), "mcp_server.py")
    # server exposes "echo"; func filter keeps only listed names
    kept = load_configured_mcp_tools([LocalMcp(name="t", transport="stdio", path=server, func=["echo"])])
    assert [t.name for t in kept] == ["echo"]
    dropped = load_configured_mcp_tools([LocalMcp(name="t", transport="stdio", path=server, func=["missing"])])
    assert dropped == []


def test_agent_ainvoke_runs_real_mcp_tool():
    from langchain_core.messages import AIMessage
    from deepagents import create_deep_agent
    from tests.fakes import FakeToolModel

    server = os.path.join(os.path.dirname(__file__), "mcp_server.py")
    tools = load_mcp_tools({"t": {"transport": "stdio", "command": sys.executable, "args": [server]}})
    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "c1"}]),
        AIMessage(content="done"),
    ])
    agent = create_deep_agent(model=model, tools=tools, system_prompt="x")
    out = asyncio.run(agent.ainvoke({"messages": [("user", "go")]}))
    contents = [str(getattr(m, "content", None)) for m in out["messages"]]
    assert any("echo:hi" in c for c in contents)  # MCP tool actually executed under ainvoke
    assert out["messages"][-1].content == "done"
