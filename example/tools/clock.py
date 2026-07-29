from datetime import datetime

from langchain_core.tools import tool


@tool
def current_time() -> str:
    """回傳現在的日期與時間。"""
    return datetime.now().isoformat()
