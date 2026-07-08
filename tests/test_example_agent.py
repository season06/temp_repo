import asyncio

from langchain_core.messages import AIMessage

from agent_template.config import AgentConfig
from agent_template.skills import Skill, MockSkillRegistry
from examples.example_agent import build_example_agent
from tests.fakes import FakeToolModel


class _Allow:
    def verify(self, context):
        return True


def _cfg():
    return AgentConfig(api_key="k", base_url="http://x/v1", model="m")


def test_build_example_agent_runs_skill_tool():
    reg = MockSkillRegistry({"greet": Skill("greet", "greeting", "hi-from-skill")})
    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "greet", "args": {}, "id": "c1"}]),
        AIMessage(content="done"),
    ])
    agent = build_example_agent(_cfg(), model=model, skill_ids=["greet"],
                                skill_registry=reg, auth_client=_Allow())
    out = asyncio.run(agent.ainvoke({"messages": [("user", "hello")]}))
    contents = [str(getattr(m, "content", None)) for m in out["messages"]]
    assert any("hi-from-skill" in c for c in contents)  # skill tool executed
    assert out["messages"][-1].content == "done"


def test_build_example_agent_default_auth_from_runtime_config_builds():
    from agent_template.config import Config
    model = FakeToolModel(scripted=[AIMessage(content="ok")])
    agent = build_example_agent(_cfg(), runtime_config=Config(auth_endpoint="http://auth/verify"), model=model)
    assert agent is not None
    out = asyncio.run(agent.ainvoke({"messages": [("user", "hi")]}))
    assert out["messages"][-1].content == "ok"
