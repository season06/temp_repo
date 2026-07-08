import pytest

from agent_template.tools import Skill, SkillRegistry, MockSkillRegistry, skill_to_tool


def test_mock_registry_get_returns_skill():
    s = Skill(name="greet", description="d", content="hello")
    reg = MockSkillRegistry({"greet": s})
    assert reg.get("greet") is s


def test_mock_registry_unknown_raises():
    reg = MockSkillRegistry({})
    with pytest.raises(KeyError):
        reg.get("nope")


def test_base_registry_not_implemented():
    with pytest.raises(NotImplementedError):
        SkillRegistry().get("x")


def test_skill_to_tool_produces_callable_tool():
    s = Skill(name="greet", description="returns a greeting", content="hi from skill")
    tool = skill_to_tool(s)
    assert tool.name == "greet"
    assert tool.description == "returns a greeting"
    assert tool.invoke({}) == "hi from skill"
