# 團隊標準化 session_stop 狀態的 MVP 約定。團隊敲定欄位/結構後,只需替換本檔。
SESSION_STOP = "session_stop"


def is_session_stop(message):
    """訊息是否帶團隊的 session_stop 狀態。

    MVP 約定（可替換）:訊息的 response_metadata 或 additional_kwargs（dict）
    帶 {"status": "session_stop"}。涵蓋 LLM 來源（AIMessage）與 tool/mcp 來源（ToolMessage）。
    """
    if message is None:
        return False
    for attr in ("response_metadata", "additional_kwargs"):
        meta = getattr(message, attr, None)
        if isinstance(meta, dict) and meta.get("status") == SESSION_STOP:
            return True
    return False


def make_session_stop_metadata():
    """建構帶 session_stop 狀態的 metadata dict。
    與 is_session_stop 共居;團隊敲定欄位/結構後,讀寫兩側一併在此檔更新。"""
    return {"status": SESSION_STOP}
