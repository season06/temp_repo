"""Skill 載入:使用 deepagent 原生 skill 機制(與 tool 概念不同)。

skill 是一個含 SKILL.md 的來源路徑,直接以 skills= 傳給 create_deep_agent,
由 deepagents 的 SkillsMiddleware 以 progressive disclosure 注入 system prompt——
不會被轉成 langchain tool。此模組只負責從 config 收集這些來源路徑。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import LocalSkill


def skill_sources(skills: list[LocalSkill]) -> list[str]:
    """從 config 的 LocalSkill 清單取出 deepagent 要的 skill 來源路徑(供 skills= 使用)。"""
    return [skill.path for skill in skills]
