from langchain.agents.middleware import AgentMiddleware

from ..errors import SecurityViolation
from ..validators import run_validators
from ._rules import detect_pii, detect_system_prompt_leak


def _final_text(messages: list):
    if not messages:
        return ""
    content = messages[-1].content
    return content if isinstance(content, str) else str(content)


class OutputValidationMiddleware(AgentMiddleware):
    """強制輸出驗證:先跑使用者自訂 validator,再跑框架強制偵測(PII + 系統提示外洩),違規即擋下。"""

    def __init__(self, output_validators: list = None):
        super().__init__()
        self._user_validators = output_validators or []

    def after_agent(self, state, runtime):
        text = _final_text(state.get("messages", []))
        violations = run_validators(text, self._user_validators)
        violations = violations + detect_pii(text) + detect_system_prompt_leak(text)
        if violations:
            raise SecurityViolation(f"output blocked: {violations}")
        return None
