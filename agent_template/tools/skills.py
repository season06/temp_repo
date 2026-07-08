from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import StructuredTool

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool


class Skill:
    """從 skill-registry 取得的 skill（MVP mock 形狀:名稱 + 描述 + 內容）。"""

    def __init__(self, name: str, description: str, content: str) -> None:
        self.name: str = name
        self.description: str = description
        self.content: str = content


class SkillRegistry:
    """skill 來源介面。正式 registry 由團隊敲定後實作;MVP 用 MockSkillRegistry。"""

    def get(self, skill_id: str) -> Skill:
        raise NotImplementedError


class MockSkillRegistry(SkillRegistry):
    def __init__(self, skills: dict[str, Skill] | None = None) -> None:
        # skills: dict[skill_id -> Skill]
        self._skills: dict[str, Skill] = skills or {}

    def get(self, skill_id: str) -> Skill:
        return self._skills[skill_id]


def skill_to_tool(skill: Skill) -> BaseTool:
    """把一個 Skill 轉成可被 agent 呼叫的 tool（MVP:無參數,回傳 skill.content）。"""

    def _run() -> str:
        return skill.content

    return StructuredTool.from_function(func=_run, name=skill.name, description=skill.description)
