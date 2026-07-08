import httpx
import pytest

from agent_template.auth import clients as auth_mod
from agent_template.auth import AuthClient, HttpAuthClient, AuthHook
from agent_template.hooks import HookContext, StopRound


class _AllowClient:
    def verify(self, context):
        return True


class _DenyClient:
    def verify(self, context):
        return False


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def test_base_auth_client_not_implemented():
    with pytest.raises(NotImplementedError):
        AuthClient().verify(None)


def test_auth_hook_allows_when_client_ok():
    hook = AuthHook(_AllowClient())
    assert hook.before_tool(HookContext(phase="before_tool", tool_name="t")) is None


def test_auth_hook_denies_with_stop_round():
    hook = AuthHook(_DenyClient())
    result = hook.before_tool(HookContext(phase="before_tool", tool_name="t"))
    assert isinstance(result, StopRound)


def test_http_auth_client_200_allows(monkeypatch):
    monkeypatch.setattr(auth_mod.httpx, "post", lambda *a, **k: _FakeResponse(200))
    client = HttpAuthClient("http://auth/verify")
    assert client.verify(HookContext(phase="before_tool", tool_name="t")) is True


def test_http_auth_client_non_200_denies(monkeypatch):
    monkeypatch.setattr(auth_mod.httpx, "post", lambda *a, **k: _FakeResponse(403))
    client = HttpAuthClient("http://auth/verify")
    assert client.verify(HookContext(phase="before_tool", tool_name="t")) is False


def test_http_auth_client_error_fails_closed(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(auth_mod.httpx, "post", boom)
    client = HttpAuthClient("http://auth/verify")
    assert client.verify(HookContext(phase="before_tool", tool_name="t")) is False


def test_http_auth_client_non_httperror_fails_closed(monkeypatch):
    def boom(*a, **k):
        raise httpx.InvalidURL("bad url")

    monkeypatch.setattr(auth_mod.httpx, "post", boom)
    client = HttpAuthClient("http://auth/verify")
    assert client.verify(HookContext(phase="before_tool", tool_name="t")) is False


def test_http_auth_client_sends_tool_name(monkeypatch):
    captured = {}

    def capture(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse(200)

    monkeypatch.setattr(auth_mod.httpx, "post", capture)
    HttpAuthClient("http://auth/verify").verify(HookContext(phase="before_tool", tool_name="mytool"))
    assert captured["json"] == {"tool": "mytool"}


def test_auth_denies_tool_end_to_end_under_ainvoke():
    import asyncio
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool
    from deepagents import create_deep_agent
    from agent_template.hooks import HookMiddleware
    from tests.fakes import FakeToolModel

    ran = []

    @tool
    def act(x: str) -> str:
        """acts"""
        ran.append(x)
        return "did:" + x

    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "act", "args": {"x": "go"}, "id": "c1"}]),
        AIMessage(content="after"),
    ])
    agent = create_deep_agent(model=model, tools=[act], system_prompt="x",
                              middleware=[HookMiddleware([AuthHook(_DenyClient())])])
    out = asyncio.run(agent.ainvoke({"messages": [("user", "go")]}))
    contents = [str(getattr(m, "content", None)) for m in out["messages"]]
    assert ran == []                # tool blocked by auth
    assert "after" not in contents  # round halted


def test_auth_allows_tool_end_to_end_under_ainvoke():
    import asyncio
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool
    from deepagents import create_deep_agent
    from agent_template.hooks import HookMiddleware
    from tests.fakes import FakeToolModel

    ran = []

    @tool
    def act(x: str) -> str:
        """acts"""
        ran.append(x)
        return "did:" + x

    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "act", "args": {"x": "go"}, "id": "c1"}]),
        AIMessage(content="after"),
    ])
    agent = create_deep_agent(model=model, tools=[act], system_prompt="x",
                              middleware=[HookMiddleware([AuthHook(_AllowClient())])])
    out = asyncio.run(agent.ainvoke({"messages": [("user", "go")]}))
    contents = [str(getattr(m, "content", None)) for m in out["messages"]]
    assert ran == ["go"]           # tool ran
    assert "after" in contents     # round continued


import asyncio


class _FakeAsyncClient:
    def __init__(self, response=None, raise_exc=None):
        self._response = response
        self._raise = raise_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        if self._raise is not None:
            raise self._raise
        return self._response


def test_base_async_auth_client_not_implemented():
    async def go():
        from agent_template.auth import AsyncAuthClient
        await AsyncAuthClient().verify(None)

    with pytest.raises(NotImplementedError):
        asyncio.run(go())


def test_async_http_auth_200_allows(monkeypatch):
    from agent_template.auth import AsyncHttpAuthClient
    monkeypatch.setattr(auth_mod.httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(response=_FakeResponse(200)))
    assert asyncio.run(AsyncHttpAuthClient("http://auth").verify(None)) is True


def test_async_http_auth_non_200_denies(monkeypatch):
    from agent_template.auth import AsyncHttpAuthClient
    monkeypatch.setattr(auth_mod.httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(response=_FakeResponse(403)))
    assert asyncio.run(AsyncHttpAuthClient("http://auth").verify(None)) is False


def test_async_http_auth_error_fails_closed(monkeypatch):
    from agent_template.auth import AsyncHttpAuthClient
    monkeypatch.setattr(auth_mod.httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(raise_exc=RuntimeError("boom")))
    assert asyncio.run(AsyncHttpAuthClient("http://auth").verify(None)) is False
