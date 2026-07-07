import asyncio
import pytest
from a2a_mvp.config import Config
from a2a_mvp.a2a_client import call_peer, RemoteNotAllowed
from a2a_mvp.tools import build_tools

CFG = Config(allowed_remote_agents=["http://peer.local"],
             outbound_service_token="svc-token")


def test_ssrf_blocklist_rejects_unlisted():
    with pytest.raises(RemoteNotAllowed):
        asyncio.run(call_peer("http://evil.local", "hi", CFG))


def test_build_tools_exposes_expected_tools():
    names = {t.name for t in build_tools(CFG)}
    assert "echo_upper" in names
    assert "call_remote_agent" in names


def test_echo_upper_local_tool():
    tool = {t.name: t for t in build_tools(CFG)}["echo_upper"]
    assert tool.invoke({"text": "abc"}) == "ABC"
