from ._envelope import wrap_system_prompt
from ._guard import InputGuardMiddleware
from ._validation import OutputValidationMiddleware


def build_security_middleware(output_validators: list = None) -> list:
    # 順序固定:輸入防護(before_agent)在前,輸出驗證(after_agent)在後。
    return [
        InputGuardMiddleware(),
        OutputValidationMiddleware(output_validators),
    ]


__all__ = ["build_security_middleware", "wrap_system_prompt"]
