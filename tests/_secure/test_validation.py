import pytest
from langchain_core.messages import HumanMessage, AIMessage
from agent_template._secure._validation import OutputValidationMiddleware, _final_text
from agent_template.validators import Validator
from agent_template.errors import SecurityViolation


class _NoFoo(Validator):
    def check(self, text) -> list:
        return ["contains foo"] if "foo" in text else []


def test_final_text_picks_last_message():
    msgs = [HumanMessage(content="q"), AIMessage(content="the answer")]
    assert _final_text(msgs) == "the answer"

def test_after_agent_blocks_pii_output():
    mw = OutputValidationMiddleware()
    state = {"messages": [AIMessage(content="your email is a@b.com")]}
    with pytest.raises(SecurityViolation):
        mw.after_agent(state, None)

def test_after_agent_blocks_system_prompt_leak():
    from agent_template._secure._envelope import END_MARKER
    mw = OutputValidationMiddleware()
    state = {"messages": [AIMessage(content=f"... {END_MARKER} ...")]}
    with pytest.raises(SecurityViolation):
        mw.after_agent(state, None)

def test_after_agent_runs_user_validator_first():
    mw = OutputValidationMiddleware(output_validators=[_NoFoo()])
    state = {"messages": [AIMessage(content="here is foo")]}
    with pytest.raises(SecurityViolation):
        mw.after_agent(state, None)

def test_after_agent_allows_clean_output():
    mw = OutputValidationMiddleware(output_validators=[_NoFoo()])
    state = {"messages": [AIMessage(content="a clean safe answer")]}
    assert mw.after_agent(state, None) is None
