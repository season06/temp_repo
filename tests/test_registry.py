import httpx
import pytest

import agent_template.core.builder as bmod
from agent_template.core import AgentBuilder
from agent_template.config import Config, LLMConfig, AgentSettings, McpsConfig, SkillsConfig, LocalMcp, RemoteRef
from agent_template.tools import HttpRegistryClient, RegistryClient


def _resp(payload):
    return httpx.Response(200, json=payload, request=httpx.Request("GET", "http://x"))


def test_empty_ref_returns_empty():
    c = HttpRegistryClient()
    assert c.resolve_mcps(RemoteRef()) == []
    assert c.resolve_skills(RemoteRef()) == []


def test_resolve_mcps_builds_local_mcp(monkeypatch):
    monkeypatch.setattr(httpx, "get",
                        lambda url, timeout: _resp({"transport": "streamable_http", "url": "https://svc/mcp", "func": ["get"]}))
    ref = RemoteRef(registry_url="https://reg", name=["weather"])
    mcps = HttpRegistryClient().resolve_mcps(ref)
    assert mcps == [LocalMcp(name="weather", transport="streamable_http", path="https://svc/mcp", func=["get"])]


def test_resolve_skills_not_implemented():
    ref = RemoteRef(registry_url="https://reg", name=["x"])
    with pytest.raises(NotImplementedError):
        HttpRegistryClient().resolve_skills(ref)


def test_resolve_failure_is_fail_loud(monkeypatch):
    def _boom(url, timeout):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx, "get", _boom)
    with pytest.raises(httpx.ConnectError):
        HttpRegistryClient().resolve_mcps(RemoteRef(registry_url="https://reg", name=["x"]))


class _FakeRegistry(RegistryClient):
    def resolve_mcps(self, ref):
        return [LocalMcp(name=n, transport="stdio", path="./r.py") for n in ref.name]

    def resolve_skills(self, ref):
        return []


def _cfg(remote_mcps=None):
    return Config(
        llm=LLMConfig(api_key="k", base_url="b", model="m"),
        agent=AgentSettings(system_prompt="x"),
        mcps=McpsConfig(local=[LocalMcp(name="local_mcp", transport="stdio", path="./l.py")],
                        remote=RemoteRef(registry_url="https://reg", name=remote_mcps or [])),
        skills=SkillsConfig(),
    )


def test_builder_appends_remote_after_local(monkeypatch):
    captured = {}
    monkeypatch.setattr(bmod, "load_configured_mcp_tools", lambda mcps: [m.name for m in mcps])
    monkeypatch.setattr(bmod, "load_skill_tools", lambda skills: [])
    monkeypatch.setattr(bmod, "get_provider_builder",
                        lambda config, hooks, tools, observability=None: captured.update(tools=tools) or "AGENT")
    AgentBuilder(_cfg(remote_mcps=["remote_mcp"]), registry=_FakeRegistry()).build()
    assert captured["tools"] == ["local_mcp", "remote_mcp"]  # remote 在 local 之後


def test_builder_skips_resolution_without_registry(monkeypatch):
    captured = {}
    monkeypatch.setattr(bmod, "load_configured_mcp_tools", lambda mcps: [m.name for m in mcps])
    monkeypatch.setattr(bmod, "load_skill_tools", lambda skills: [])
    monkeypatch.setattr(bmod, "get_provider_builder",
                        lambda config, hooks, tools, observability=None: captured.update(tools=tools) or "AGENT")
    AgentBuilder(_cfg(remote_mcps=["remote_mcp"])).build()  # 無 registry
    assert captured["tools"] == ["local_mcp"]  # remote 完全跳過
