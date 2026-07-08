from langchain_core.tools import StructuredTool


class Skill:
    """從 skill-registry 取得的 skill（MVP mock 形狀:名稱 + 描述 + 內容）。"""

    def __init__(self, name, description, content):
        self.name = name
        self.description = description
        self.content = content


class SkillRegistry:
    """skill 來源介面。正式 registry 由團隊敲定後實作;MVP 用 MockSkillRegistry。"""

    def get(self, skill_id):
        raise NotImplementedError


class MockSkillRegistry(SkillRegistry):
    def __init__(self, skills=None):
        # skills: dict[skill_id -> Skill]
        self._skills = skills or {}

    def get(self, skill_id):
        return self._skills[skill_id]


def skill_to_tool(skill):
    """把一個 Skill 轉成可被 agent 呼叫的 tool（MVP:無參數,回傳 skill.content）。"""

    def _run():
        return skill.content

    return StructuredTool.from_function(func=_run, name=skill.name, description=skill.description)
