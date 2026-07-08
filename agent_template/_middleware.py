from langchain.agents.middleware import AgentMiddleware, hook_config

from .hooks import HookContext, StopRound
from .session import is_session_stop


class HookMiddleware(AgentMiddleware):
    """把 SDK Hooks + 內建 session_stop 翻譯成 langchain AgentMiddleware。
    這是唯一知道 langchain middleware 的模組;未來換框架由該框架的 adapter 另作翻譯。"""

    def __init__(self, hooks):
        super().__init__()
        self._hooks = list(hooks)

    @hook_config(can_jump_to=["end"])
    def before_model(self, state, runtime):
        messages = state["messages"]
        last = messages[-1] if messages else None
        # tool/mcp 來源的 session_stop 在此被捕捉（tool 之後、下一次 LLM 之前）
        if is_session_stop(last):
            return {"jump_to": "end"}
        context = HookContext(phase="before_llm", messages=messages)
        for hook in self._hooks:
            if isinstance(hook.before_llm(context), StopRound):
                return {"jump_to": "end"}
        return None

    @hook_config(can_jump_to=["end"])
    def after_model(self, state, runtime):
        messages = state["messages"]
        last = messages[-1] if messages else None
        # LLM 來源的 session_stop
        if is_session_stop(last):
            return {"jump_to": "end"}
        context = HookContext(phase="after_llm", messages=messages, result=last)
        for hook in self._hooks:
            if isinstance(hook.after_llm(context), StopRound):
                return {"jump_to": "end"}
        return None
