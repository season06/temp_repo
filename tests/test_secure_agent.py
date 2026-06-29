"""build_agent returns a SecureAgent that delegates invoke but blocks streaming
(streaming would emit output before after_agent validation runs — C1)."""
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


@pytest.mark.parametrize("method", ["stream", "astream", "astream_events", "astream_log"])
def test_streaming_methods_blocked(monkeypatch, method):
    agent = _agent(monkeypatch)
    with pytest.raises(SecurityViolation):
        getattr(agent, method)  # attribute access alone must raise


def test_non_streaming_attrs_still_reachable(monkeypatch):
    agent = _agent(monkeypatch)
    # a normal Runnable/graph attribute delegates through to the wrapped agent
    assert callable(agent.invoke)
    assert hasattr(agent, "get_graph")
