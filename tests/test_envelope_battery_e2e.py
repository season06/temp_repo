"""End-to-end battery: run the full block/allow battery through a REAL built agent.

This proves the assembled middleware stack (InputGuardMiddleware before_agent +
OutputValidationMiddleware after_agent, wired by build_agent) blocks/passes exactly
as the rule-level oracle (tests/_secure/test_battery.py) does — no wiring drift.
"""
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage

import agent_template.factory as factory
from agent_template import build_agent, AgentConfig
from agent_template.errors import SecurityViolation
from tests._secure.battery_data import BLOCK_TESTS, ALLOW_TESTS

_CLEAN_OUTPUT = "ok"
_CLEAN_INPUT = "what is the weather today?"


class _ToolFake(GenericFakeChatModel):
    def bind_tools(self, *a, **k):
        return self


def _build(output_text, monkeypatch):
    fake = _ToolFake(messages=iter([AIMessage(content=output_text)]))
    monkeypatch.setattr(factory, "build_chat_model", lambda config: fake)
    cfg = AgentConfig(model="m", base_url="https://x/v1", api_key="k", enable_audit_log=False)
    return build_agent("answer questions", config=cfg)


@pytest.mark.parametrize("layer,value,why", BLOCK_TESTS)
def test_block_e2e(layer, value, why, monkeypatch):
    if layer == "input":
        agent = _build(_CLEAN_OUTPUT, monkeypatch)
        invocation = {"messages": [HumanMessage(content=value)]}
    else:
        agent = _build(value, monkeypatch)
        invocation = {"messages": [HumanMessage(content=_CLEAN_INPUT)]}
    with pytest.raises(SecurityViolation):
        agent.invoke(invocation)


@pytest.mark.parametrize("layer,value,why", ALLOW_TESTS)
def test_allow_e2e(layer, value, why, monkeypatch):
    if layer == "input":
        agent = _build(_CLEAN_OUTPUT, monkeypatch)
        out = agent.invoke({"messages": [HumanMessage(content=value)]})
        assert out["messages"][-1].content == _CLEAN_OUTPUT
    else:
        agent = _build(value, monkeypatch)
        out = agent.invoke({"messages": [HumanMessage(content=_CLEAN_INPUT)]})
        assert out["messages"][-1].content == value
