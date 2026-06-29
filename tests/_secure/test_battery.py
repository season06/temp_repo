"""Rule-level adversarial battery: every BLOCK case must flag, every ALLOW case must not."""
import pytest

from agent_template._secure._rules import (
    detect_prompt_injection,
    detect_pii,
    detect_system_prompt_leak,
)
from tests._secure.battery_data import BLOCK_TESTS, ALLOW_TESTS


def _flags(layer, value) -> list:
    if layer == "input":
        return detect_prompt_injection(value)
    return detect_pii(value) + detect_system_prompt_leak(value)


@pytest.mark.parametrize("layer,value,why", BLOCK_TESTS)
def test_block_battery(layer, value, why):
    assert _flags(layer, value), f"should be BLOCKED ({why}): {value!r}"


@pytest.mark.parametrize("layer,value,why", ALLOW_TESTS)
def test_allow_battery(layer, value, why):
    assert _flags(layer, value) == [], f"should be ALLOWED ({why}): {value!r}"
