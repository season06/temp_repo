"""Skill 載入:把 config 宣告的本地 skill(一個 @tool python 檔)載入成 langchain tools。

deepagent 使用 tool 的方式就是把 langchain BaseTool 餵給 create_deep_agent(tools=...)。
一個 skill 檔即一個(或多個)`@tool` 函式;載入時收集檔內所有 BaseTool 物件。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from langchain_core.tools import tool, BaseTool


def load_skill_file(path: str) -> list[BaseTool]:
    """匯入單一 skill python 檔,回傳檔內所有 langchain BaseTool(即 @tool 產生的物件)。"""
    module_name = "_agent_template_skill_" + Path(path).stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load skill file: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [obj for obj in vars(module).values() if isinstance(obj, BaseTool)]

a = load_skill_file('./skill.py')