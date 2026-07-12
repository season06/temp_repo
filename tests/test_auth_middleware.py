import asyncio

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from deepagents import create_deep_agent

from agent_template.hooks import AuthMiddleware, AuthenticationError, HookMiddleware
from agent_template.auth.clients import AuthContext
from agent_template.auth import AuthHook
from tests.fakes import FakeToolModel


class _Allow:
    def __init__(self):
        self.calls = 0

    def verify(self, context):
        self.calls += 1
        return True


class _Deny:
    def verify(self, context):
        return False


class _RT:
    def __init__(self, context):
        self.context = context


def test_auth_middleware_allows_when_identity_and_client_ok():
    mw = AuthMiddleware(_Allow())
    assert mw.before_agent({}, _RT(AuthContext(identity="u1"))) is None


def test_auth_middleware_denies_raises():
    mw = AuthMiddleware(_Deny())
    with pytest.raises(AuthenticationError):
        mw.before_agent({}, _RT(AuthContext(identity="u1")))


def test_auth_middleware_missing_identity_raises_without_calling_client():
    client = _Allow()
    mw = AuthMiddleware(client)
    with pytest.raises(AuthenticationError):
        mw.before_agent({}, _RT(AuthContext()))          # identity=None
    assert client.calls == 0                              # 未打網路,純 fail-closed


def test_auth_middleware_none_context_raises():
    mw = AuthMiddleware(_Allow())
    with pytest.raises(AuthenticationError):
        mw.before_agent({}, _RT(None))


def _agent(client):
    return create_deep_agent(
        model=FakeToolModel(scripted=[AIMessage(content="ok")]),
        tools=[], system_prompt="x",
        middleware=[AuthMiddleware(client)],
    )


def test_entry_auth_denies_invoke_end_to_end():
    with pytest.raises(AuthenticationError):
        _agent(_Deny()).invoke({"messages": [("user", "hi")]}, context={"identity": "u1"})


def test_entry_auth_allows_invoke_end_to_end():
    out = _agent(_Allow()).invoke({"messages": [("user", "hi")]}, context={"identity": "u1"})
    assert out["messages"][-1].content == "ok"


def test_entry_auth_denies_ainvoke_end_to_end():
    with pytest.raises(AuthenticationError):
        asyncio.run(_agent(_Deny()).ainvoke({"messages": [("user", "hi")]}, context={"identity": "u1"}))


def test_per_tool_auth_receives_caller_identity_end_to_end():
    seen = []

    class _CaptureClient:
        def verify(self, context):
            seen.append(getattr(context, "identity", None))
            return True

    @tool
    def act(x: str) -> str:
        """acts"""
        return "did:" + x

    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "act", "args": {"x": "go"}, "id": "c1"}]),
        AIMessage(content="after"),
    ])
    agent = create_deep_agent(
        model=model, tools=[act], system_prompt="x",
        middleware=[HookMiddleware([AuthHook(_CaptureClient())])],
        context_schema=AuthContext,
    )
    agent.invoke({"messages": [("user", "go")]}, context={"identity": "alice"})
    assert "alice" in seen
