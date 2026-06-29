"""build_agent returns a SecureAgent allow-list wrapper: only the validated
invoke-family is exposed; streaming AND compose methods (which return raw
re-streamable runnables) are blocked, closing the C1 output-validation bypass."""
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage

import agent_template.factory as factory
from agent_template import build_agent, AgentConfig
from agent_template.errors import SecurityViolation


class _ToolFake(GenericFakeChatModel):
    def bind_tools(self, *a, **k):
        return self


def _agent(monkeypatch):
    fake = _ToolFake(messages=iter([AIMessage(content="a safe answer")]))
    monkeypatch.setattr(factory, "build_chat_model", lambda config: fake)
    cfg = AgentConfig(model="m", base_url="https://x/v1", api_key="k", enable_audit_log=False)
    return build_agent("answer questions", config=cfg)


def test_invoke_delegates(monkeypatch):
    agent = _agent(monkeypatch)
    out = agent.invoke({"messages": [HumanMessage(content="hello")]})
    assert out["messages"][-1].content == "a safe answer"


# Every known way to obtain unvalidated streamed output, plus the compose
# methods that hand back a raw re-streamable runnable, must be blocked.
@pytest.mark.parametrize("name", [
    "stream", "astream", "astream_events", "astream_log", "stream_events",
    "transform", "atransform",
    "with_config", "bind", "with_retry", "with_fallbacks", "with_types",
    "with_listeners", "pipe",
    "get_graph", "nodes", "builder", "steps", "channels",
    "_agent",  # name-mangled inner ref: casual ._agent discovery is blocked too
])
def test_blocked_surface_raises_security_violation(monkeypatch, name):
    agent = _agent(monkeypatch)
    with pytest.raises(SecurityViolation):
        getattr(agent, name)


@pytest.mark.parametrize("name", ["stream", "astream", "with_config", "pipe"])
def test_hasattr_probe_is_graceful_false(monkeypatch, name):
    # capability probing must NOT crash — blocked attr is also an AttributeError
    agent = _agent(monkeypatch)
    assert hasattr(agent, name) is False


def test_compose_then_stream_is_unreachable(monkeypatch):
    # the with_config(...).stream(...) bypass: with_config itself is blocked
    agent = _agent(monkeypatch)
    with pytest.raises(SecurityViolation):
        agent.with_config({})
