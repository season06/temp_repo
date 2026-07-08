from __future__ import annotations

from typing import Any

from collections.abc import Callable

from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain_core.messages import ToolMessage

from .hooks import Hook, HookContext, StopRound
from .session import is_session_stop, make_session_stop_metadata


class HookMiddleware(AgentMiddleware):
    """把 SDK Hooks + 內建 session_stop 翻譯成 langchain AgentMiddleware。
    這是唯一知道 langchain middleware 的模組;未來換框架由該框架的 adapter 另作翻譯。"""

    def __init__(self, hooks: list[Hook]) -> None:
        super().__init__()
        self._hooks = list(hooks)

    @hook_config(can_jump_to=["end"])
    def before_model(self, state: dict, runtime: Any) -> dict | None:
        messages = state["messages"]
        last = messages[-1] if messages else None
        # tool/mcp 來源的 session_stop 在此被捕捉（tool 之後、下一次 LLM 之前）
        # MVP 限制:僅檢查最後一則訊息。單一 tool call 下必為正確;
        # 若 LLM 產生「平行 tool calls」且非最後一個回 session_stop,此處會漏接。
        # 待 P3 接真實 MCP、確有平行 tool 時再處理(掃描尾端附加訊息)。
        if is_session_stop(last):
            return {"jump_to": "end"}
        context = HookContext(phase="before_llm", messages=messages)
        for hook in self._hooks:
            if isinstance(hook.before_llm(context), StopRound):
                return {"jump_to": "end"}
        return None

    @hook_config(can_jump_to=["end"])
    def after_model(self, state: dict, runtime: Any) -> dict | None:
        messages = state["messages"]
        last = messages[-1] if messages else None
        # LLM 來源的 session_stop
        # 見 before_model 的 MVP 限制註解(僅檢查最後一則）。
        if is_session_stop(last):
            return {"jump_to": "end"}
        context = HookContext(phase="after_llm", messages=messages, result=last)
        for hook in self._hooks:
            if isinstance(hook.after_llm(context), StopRound):
                return {"jump_to": "end"}
        return None

    def wrap_tool_call(self, request: Any, handler: Callable) -> Any:
        tool_call = request.tool_call
        blocked = self._run_before_tool(tool_call)
        if blocked is not None:
            return blocked
        return self._run_after_tool(tool_call, handler(request))

    async def awrap_tool_call(self, request: Any, handler: Callable) -> Any:
        # MCP tool 為 async-only → agent 走 ainvoke;langchain 的 awrap_tool_call
        # 不會 fallback 到 sync 版,故必須提供本方法,hooks/auth 才會在 async 執行下生效。
        tool_call = request.tool_call
        blocked = self._run_before_tool(tool_call)
        if blocked is not None:
            return blocked
        return self._run_after_tool(tool_call, await handler(request))

    def _run_before_tool(self, tool_call: dict) -> Any | None:
        context = HookContext(phase="before_tool", tool_name=tool_call["name"], tool_args=tool_call.get("args"))
        for hook in self._hooks:
            outcome = hook.before_tool(context)
            if isinstance(outcome, StopRound):
                return self._stop_message(tool_call, outcome.reason or "stopped by hook")
        return None

    def _run_after_tool(self, tool_call: dict, result: Any) -> Any:
        context = HookContext(phase="after_tool", tool_name=tool_call["name"], tool_args=tool_call.get("args"), result=result)
        for hook in self._hooks:
            outcome = hook.after_tool(context)
            if isinstance(outcome, StopRound):
                return self._stop_message(tool_call, outcome.reason or getattr(result, "content", "stopped by hook"))
        return result

    def _stop_message(self, tool_call: dict, content: str) -> ToolMessage:
        # 合成一則帶 session_stop 標記的 ToolMessage;下一個 before_model 會據此中止該輪。
        return ToolMessage(
            content=content,
            tool_call_id=tool_call["id"],
            name=tool_call["name"],
            response_metadata=make_session_stop_metadata(),
        )
