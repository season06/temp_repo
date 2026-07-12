from agent_template.config import LocalSkill
from agent_template.tools import skill_sources


def test_skill_sources_extracts_paths():
    skills = [LocalSkill(name="a", path="/skills/a"), LocalSkill(name="b", path="/skills/b")]
    assert skill_sources(skills) == ["/skills/a", "/skills/b"]


def test_skill_sources_empty_list():
    assert skill_sources([]) == []
