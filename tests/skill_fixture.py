"""測試用 skill 檔:定義一個 @tool,供 load_skill_tools 載入。"""

from langchain_core.tools import tool


@tool
def greet() -> str:
    """returns a greeting"""
    return "hi-from-skill"
