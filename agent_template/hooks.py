class StopRound:
    """由 Hook 方法回傳（或由內建 session_stop 檢查產生）以中止當前的 agent 執行（一輪）。"""

    def __init__(self, reason=None):
        self.reason = reason


class HookContext:
    """傳入 Hook 方法的生命週期資料。

    phase: "before_llm" | "after_llm" | "before_tool" | "after_tool"
    messages: 當前對話訊息（list）— llm 階段使用
    tool_name / tool_args: tool 階段使用
    result: after_llm 的 AI 訊息 / after_tool 的 tool 結果
    """

    def __init__(self, phase, messages=None, tool_name=None, tool_args=None, result=None):
        self.phase = phase
        self.messages = messages
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.result = result


class Hook:
    """開發者面對的生命週期 hook。繼承並覆寫需要的節點。
    每個方法回傳 None 表示繼續,回傳 StopRound 表示中止該輪。"""

    def before_llm(self, context):
        return None

    def after_llm(self, context):
        return None

    def before_tool(self, context):
        return None

    def after_tool(self, context):
        return None
