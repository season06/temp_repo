from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage

from ..errors import SecurityViolation
from ._rules import detect_prompt_injection


def _latest_human_text(messages: list):
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content if isinstance(msg.content, str) else str(msg.content)
    return ""


class InputGuardMiddleware(AgentMiddleware):
    """強制輸入防護:進入 agent 前偵測 prompt injection,違規即擋下。"""

    def before_agent(self, state, runtime):
        text = _latest_human_text(state.get("messages", []))
        violations = detect_prompt_injection(text)
        if violations:
            raise SecurityViolation(f"input blocked: {violations}")
        return None
