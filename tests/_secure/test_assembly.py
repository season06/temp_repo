from agent_template._secure import build_security_middleware, wrap_system_prompt
from agent_template._secure._guard import InputGuardMiddleware
from agent_template._secure._validation import OutputValidationMiddleware
from agent_template.validators import Validator


class _V(Validator):
    def check(self, text) -> list:
        return []


def test_build_returns_guard_then_validation():
    mw = build_security_middleware()
    assert len(mw) == 2
    assert isinstance(mw[0], InputGuardMiddleware)
    assert isinstance(mw[1], OutputValidationMiddleware)

def test_user_validators_passed_into_output_middleware():
    v = _V()
    mw = build_security_middleware(output_validators=[v])
    assert v in mw[1]._user_validators

def test_wrap_system_prompt_reexported():
    assert wrap_system_prompt("x").endswith(  # suffix present
        __import__("agent_template._secure._envelope", fromlist=["SAFETY_SUFFIX"]).SAFETY_SUFFIX
    )
