from abc import ABC, abstractmethod


class Validator(ABC):
    """使用者自訂驗證的基底。check 回傳違規描述清單,空清單代表通過。"""

    @abstractmethod
    def check(self, text) -> list:
        ...


def run_validators(text, validators: list = None) -> list:
    if not validators:
        return []
    violations = []
    for v in validators:
        violations.extend(v.check(text))
    return violations
