import pytest
from agent_template.validators import Validator, run_validators


class _Banned(Validator):
    def check(self, text) -> list:
        return ["banned word"] if "banned" in text else []


def test_validator_is_abstract():
    with pytest.raises(TypeError):
        Validator()

def test_run_validators_collects_violations():
    out = run_validators("this is banned", [_Banned()])
    assert out == ["banned word"]

def test_run_validators_clean():
    assert run_validators("ok", [_Banned()]) == []

def test_run_validators_none():
    assert run_validators("anything", None) == []
