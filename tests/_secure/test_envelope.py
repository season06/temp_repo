# tests/_secure/test_envelope.py
from agent_template._secure._envelope import (
    wrap_system_prompt, SAFETY_PREFIX, SAFETY_SUFFIX,
)


def test_wrap_sandwiches_task_prompt():
    out = wrap_system_prompt("You answer billing questions.")
    assert out.startswith(SAFETY_PREFIX)
    assert out.endswith(SAFETY_SUFFIX)
    assert "You answer billing questions." in out

def test_wrap_none_task_prompt():
    out = wrap_system_prompt(None)
    assert out.startswith(SAFETY_PREFIX)
    assert out.endswith(SAFETY_SUFFIX)

def test_prefix_and_suffix_nonempty():
    assert SAFETY_PREFIX.strip()
    assert SAFETY_SUFFIX.strip()
