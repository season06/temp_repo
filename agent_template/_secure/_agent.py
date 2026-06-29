from ..errors import SecurityViolation

# 串流方法會在 after_agent 強制輸出驗證「之前」就把 chunk 吐給呼叫端,
# 本質上繞過輸出驗證。P2 先一律停用(明確報錯);驗證過的串流延到 P3。
_STREAMING_METHODS = frozenset({"stream", "astream", "astream_events", "astream_log"})


class SecureAgent:
    """包住 deepagents agent:invoke/ainvoke/batch 等照常委派(都會跑完整圖、
    經過 after_agent 強制驗證);串流方法則停用以免繞過輸出驗證。"""

    def __init__(self, agent):
        object.__setattr__(self, "_agent", agent)

    def __getattr__(self, name):
        if name in _STREAMING_METHODS:
            raise SecurityViolation(
                f"{name}() 在強制輸出驗證下停用:串流會在輸出驗證前就吐出內容、"
                f"繞過 after_agent 檢查。請改用 invoke()/ainvoke();"
                f"驗證過的串流預計於 P3 提供。"
            )
        return getattr(self._agent, name)
