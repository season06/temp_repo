import pytest

from agent_template.loaders import mcp
from agent_template.config import McpServer


class FakeClient:
    last_connections = None

    def __init__(self, connections):
        FakeClient.last_connections = connections

    async def get_tools(self):
        return ["tool-a", "tool-b"]


class BoomClient:
    def __init__(self, connections):
        pass

    async def get_tools(self):
        raise ConnectionError("connection refused")


def test_success_collects_tools_and_translates_transport(monkeypatch):
    monkeypatch.setattr(mcp, "MultiServerMCPClient", FakeClient)
    servers = [McpServer(name="wiki", url="http://x/mcp")]
    assert mcp.load_mcp_tools(servers) == ["tool-a", "tool-b"]
    # config 用連字號,adapters 要底線 —— 翻譯發生在這層
    assert FakeClient.last_connections == {
        "wiki": {"transport": "streamable_http", "url": "http://x/mcp"}
    }


def test_headers_passed_to_connection(monkeypatch):
    monkeypatch.setattr(mcp, "MultiServerMCPClient", FakeClient)
    servers = [McpServer(name="wiki", url="http://x/mcp")]
    mcp.load_mcp_tools(servers, headers={"Authorization": "Bearer tk"})
    assert FakeClient.last_connections["wiki"]["headers"] == {"Authorization": "Bearer tk"}


def test_no_headers_key_when_none(monkeypatch):
    monkeypatch.setattr(mcp, "MultiServerMCPClient", FakeClient)
    mcp.load_mcp_tools([McpServer(name="wiki", url="http://x/mcp")])
    assert "headers" not in FakeClient.last_connections["wiki"]


def test_failure_warns_and_skips_server(monkeypatch):
    monkeypatch.setattr(mcp, "MultiServerMCPClient", BoomClient)
    with pytest.warns(UserWarning, match="wiki.*連線失敗"):
        assert mcp.load_mcp_tools([McpServer(name="wiki", url="http://x/mcp")]) == []


def test_one_bad_server_does_not_block_good_one(monkeypatch):
    calls = []

    class Mixed:
        def __init__(self, connections):
            self.name = next(iter(connections))

        async def get_tools(self):
            calls.append(self.name)
            if self.name == "bad":
                raise ConnectionError("refused")
            return ["ok-tool"]

    monkeypatch.setattr(mcp, "MultiServerMCPClient", Mixed)
    servers = [
        McpServer(name="bad", url="http://bad/mcp"),
        McpServer(name="good", url="http://good/mcp"),
    ]
    with pytest.warns(UserWarning, match="bad"):
        assert mcp.load_mcp_tools(servers) == ["ok-tool"]
    assert calls == ["bad", "good"]


def test_unsupported_transport_warns_and_skips():
    server = McpServer(name="local", transport="stdio", url="unused")
    with pytest.warns(UserWarning, match="stdio.*尚未支援"):
        assert mcp.load_mcp_tools([server]) == []
