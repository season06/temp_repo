import asyncio
import os
import sys

from agent_template import mcp as mcp_mod
from agent_template.mcp import load_mcp_tools


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
