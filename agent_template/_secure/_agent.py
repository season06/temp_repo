from ..errors import SecurityViolation

# 只開放「會跑完整圖、經過 after_agent 強制輸出驗證」且回傳彙整結果(非串流 chunk)
# 的方法。其餘一律封鎖 —— 特別是串流(stream/astream/stream_events/transform...)
# 以及會回傳「未包裝、可再串流」Runnable 的組合方法(with_config/bind/pipe/
# with_retry/with_fallbacks...)。採 allow-list 而非 deny-list,以免遺漏進入點。
_ALLOWED = frozenset({"invoke", "ainvoke", "batch", "abatch"})


class _BlockedAttribute(SecurityViolation, AttributeError):
    """同時是 SecurityViolation 與 AttributeError:
    - 直接取用/呼叫被封鎖方法 → 視為 SecurityViolation(明確、響亮)。
    - hasattr()/capability 探測 → 因是 AttributeError 而優雅得到 False,
      不會炸掉合法的 invoke 流程(框架常以 hasattr 探測串流能力)。"""


class SecureAgent:
    """包住 deepagents agent,只暴露經強制輸出驗證的 invoke/ainvoke/batch/abatch;
    串流與會回傳未包裝 Runnable 的組合方法一律封鎖,避免繞過 after_agent 驗證。
    驗證過的串流延到 P3。"""

    def __init__(self, agent):
        object.__setattr__(self, "_agent", agent)

    def __getattr__(self, name):
        if name in _ALLOWED:
            return getattr(self._agent, name)
        if name.startswith("__") and name.endswith("__"):
            # 讓 dunder 探測(copy/pickle/repr 等)以標準 AttributeError 收場
            raise AttributeError(name)
        raise _BlockedAttribute(
            f"SecureAgent 不開放 {name!r}:僅允許 invoke/ainvoke/batch/abatch。"
            f"串流與組合方法已停用以免繞過強制輸出驗證;驗證過的串流預計於 P3 提供。"
        )
