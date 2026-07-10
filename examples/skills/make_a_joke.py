"""範例 skill 檔。

skill 檔 = 一支含 `@tool` 的 python 檔;load_skill_file 會收集檔內所有
langchain BaseTool。這裡只放一個 tool。
"""

from langchain_core.tools import tool


@tool
def make_a_joke(topic: str) -> str:
    """Tell a short joke about the given topic."""
    return f"Why did the {topic} sit on the computer? To keep an eye on the mouse!"
