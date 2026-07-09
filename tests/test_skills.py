import os

import pytest

from agent_template.config import LocalSkill
from agent_template.tools import load_skill_file, load_skill_tools

SKILL_FIXTURE = os.path.join(os.path.dirname(__file__), "skill_fixture.py")


def test_load_skill_file_collects_tools():
    tools = load_skill_file(SKILL_FIXTURE)
    names = [t.name for t in tools]
    assert "greet" in names
    greet = next(t for t in tools if t.name == "greet")
    assert greet.description == "returns a greeting"
    assert greet.invoke({}) == "hi-from-skill"


def test_load_skill_tools_over_list():
    tools = load_skill_tools([LocalSkill(name="greet", path=SKILL_FIXTURE)])
    assert [t.name for t in tools] == ["greet"]


def test_load_skill_tools_empty_list():
    assert load_skill_tools([]) == []


def test_load_skill_file_missing_raises():
    with pytest.raises((FileNotFoundError, ImportError)):
        load_skill_file("/no/such/skill.py")
