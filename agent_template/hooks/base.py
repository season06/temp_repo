from __future__ import annotations

from typing import Any


class StopRound:
    """由 Hook 方法回傳（或由內建 session_stop 檢查產生）以中止當前的 agent 執行（一輪）。"""

    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason


class HookContext:
    """傳入 Hook 方法的生命週期資料。

    phase: "before_llm" | "after_llm" | "before_tool" | "after_tool"
    messages: 當前對話訊息（list）— llm 階段使用
    tool_name / tool_args: tool 階段使用
    result: after_llm 的 AI 訊息 / after_tool 的 tool 結果
    identity: 呼叫端身分（來自 runtime.context），per-tool auth 用
    """

    def __init__(
        self,
        phase: str,
        messages: list | None = None,
        tool_name: str | None = None,
        tool_args: dict | None = None,
        result: Any = None,
        identity: str | None = None,
    ) -> None:
        self.phase = phase
        self.messages = messages
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.result = result
        self.identity = identity


class Hook:
    """開發者面對的生命週期 hook。繼承並覆寫需要的節點。
    每個方法回傳 None 表示繼續,回傳 StopRound 表示中止該輪。"""

    def before_llm(self, context: HookContext) -> StopRound | None:
        return None

    def after_llm(self, context: HookContext) -> StopRound | None:
        return None

    def before_tool(self, context: HookContext) -> StopRound | None:
        return None

    def after_tool(self, context: HookContext) -> StopRound | None:
        return None


class AuthenticationError(Exception):
    """入口身分認證未通過時由 AuthMiddleware 拋出;呼叫端可據此與一般錯誤區分。"""
