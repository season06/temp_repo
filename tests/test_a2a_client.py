import pytest

from agent_template.config import A2aAgent
from agent_template.loaders import a2a


class FakeCard:
    def __init__(self, name="remote", description="answers research questions"):
        self.name = name
        self.description = description


def test_load_a2a_tools_uses_card_description(monkeypatch):
    async def fake_fetch(url):
        assert url == "http://other:9000"
        return FakeCard()

    monkeypatch.setattr(a2a, "_fetch_card", fake_fetch)
    tools = a2a.load_a2a_tools([A2aAgent(name="research", url="http://other:9000")])
    assert len(tools) == 1
    assert tools[0].name == "research"
    assert tools[0].description == "answers research questions"


def test_empty_description_falls_back_to_name(monkeypatch):
    async def fake_fetch(url):
        return FakeCard(description="")

    monkeypatch.setattr(a2a, "_fetch_card", fake_fetch)
    tools = a2a.load_a2a_tools([A2aAgent(name="r", url="http://x")])
    assert "remote" in tools[0].description


def test_card_fetch_failure_warns_and_skips(monkeypatch):
    async def boom(url):
        raise ConnectionError("refused")

    monkeypatch.setattr(a2a, "_fetch_card", boom)
    with pytest.warns(UserWarning, match="ghost.*card 抓取失敗"):
        tools = a2a.load_a2a_tools([A2aAgent(name="ghost", url="http://down")])
    assert tools == []


def test_tool_invokes_call_a2a(monkeypatch):
    import asyncio

    async def fake_fetch(url):
        return FakeCard()

    async def fake_call(url, query, headers=None):
        return f"answer to {query} from {url}"

    monkeypatch.setattr(a2a, "_fetch_card", fake_fetch)
    monkeypatch.setattr(a2a, "call_a2a", fake_call)
    tools = a2a.load_a2a_tools([A2aAgent(name="r", url="http://x")])
    # a2a tool 是 async-only(同 mcp tool);agent 執行一律走 async 路徑
    result = asyncio.run(tools[0].ainvoke({"query": "hi"}))
    assert result == "answer to hi from http://x"
