"""Skill 載入:把 config 宣告的本地 skill(一個 @tool python 檔)載入成 langchain tools。

deepagent 使用 tool 的方式就是把 langchain BaseTool 餵給 create_deep_agent(tools=...)。
一個 skill 檔即一個(或多個)`@tool` 函式;載入時收集檔內所有 BaseTool 物件。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from langchain_core.tools import tool, BaseTool


@tool
def greet() -> str:
    """returns a greeting"""
    return "hi-from-skill"
