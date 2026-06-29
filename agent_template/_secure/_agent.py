from ..errors import SecurityViolation

# 只開放「會跑完整圖、經過 after_agent 強制輸出驗證」且回傳彙整結果(非串流 chunk)
# 的方法。其餘一律封鎖 —— 串流(stream/astream/stream_events/transform...)以及會
# 回傳「未包裝、可再串流」Runnable 的組合方法(with_config/bind/pipe/with_retry...)。
# 採 allow-list 而非 deny-list,以免遺漏進入點。
_ALLOWED = frozenset({"invoke", "ainvoke", "batch", "abatch"})

_INNER = "_SecureAgent__agent"  # name-mangled inner reference


class _BlockedAttribute(SecurityViolation, AttributeError):
    """同時是 SecurityViolation 與 AttributeError:
    - 直接取用/呼叫被封鎖屬性 → 視為 SecurityViolation(明確、響亮)。
    - hasattr()/capability 探測 → 因是 AttributeError 而優雅得到 False,
      不會炸掉合法的 invoke 流程(框架常以 hasattr 探測串流能力)。"""


class SecureAgent:
    """包住 deepagents agent,只暴露經強制輸出驗證的 invoke/ainvoke/batch/abatch
    (皆跑完整圖、回傳彙整結果);串流與會回傳未包裝 Runnable 的組合方法一律封鎖,
    避免繞過 after_agent 驗證。需逐次設定請用 `invoke(input, config=...)`;
    `with_config` / `get_graph` 等已不開放。驗證過的串流延到 P3。

    限制(model A 固有,已書面接受):純 Python 包裝無法完全隱藏被包物件 ——
    刻意者仍可經 `__dict__` / `vars()` / `gc` 取得內層 graph 直接串流。本層的目標
    是擋住「意外誤用」並提高刻意繞過的門檻;真正的內部化由 P3 編譯 `_secure/`
    進一步提高,完全強制則需 server 端(model B)。詳見
    docs/superpowers/specs/p2-redteam-deferred-to-p3.md。"""

    def __init__(self, agent):
        object.__setattr__(self, _INNER, agent)

    def __getattr__(self, name):
        # _INNER 一般情況下走正常查找(在 __dict__),不會進到這裡;
        # 若缺失則回標準 AttributeError,避免誤報成 SecurityViolation。
        if name == _INNER:
            raise AttributeError(name)
        if name in _ALLOWED:
            return getattr(self.__agent, name)
        if name.startswith("__") and name.endswith("__"):
            # 讓 dunder 探測(copy/pickle/repr 等)以標準 AttributeError 收場
            raise AttributeError(name)
        raise _BlockedAttribute(
            f"SecureAgent 不開放 {name!r}:僅允許 invoke/ainvoke/batch/abatch。"
            f"串流與組合方法已停用以免繞過強制輸出驗證;驗證過的串流預計於 P3 提供。"
        )
