import asyncio
import os

from langchain_core.messages import AIMessage

import agent_template.core.factory as factory
from agent_template.config import Config, LLMConfig, AgentSettings, SkillsConfig, AuthConfig, LocalSkill
from examples.agent import build_example_agent
from tests.fakes import FakeToolModel

SKILL_FIXTURE = os.path.join(os.path.dirname(__file__), "skill_src")


class _Allow:
    def verify(self, context):
        return True


def _cfg(**over):
    base = dict(llm=LLMConfig(api_key="k", base_url="http://x/v1", model="m"),
                agent=AgentSettings(system_prompt="x"),
                auth=AuthConfig(endpoint="http://auth/verify"))
    base.update(over)
    return Config(**base)


def test_build_example_agent_wires_skill_source(monkeypatch):
    monkeypatch.setattr(factory, "HttpAuthClient", lambda ep: _Allow())   # 入口 auth 放行
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    captured = {}
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: captured.update(k) or "AGENT")
    cfg = _cfg(skills=SkillsConfig(local=[LocalSkill(name="greet", path=SKILL_FIXTURE)]))
    build_example_agent(cfg)
    assert SKILL_FIXTURE in captured["skills"]   # skill 以來源路徑接上 deepagent skills=(非 tool)


def test_build_example_agent_default_auth_from_config_builds(monkeypatch):
    monkeypatch.setattr(factory, "HttpAuthClient", lambda ep: _Allow())   # 入口 auth 放行
    cfg = _cfg()
    model = FakeToolModel(scripted=[AIMessage(content="ok")])
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: model)
    agent = build_example_agent(cfg)
    assert agent is not None
    out = asyncio.run(agent.ainvoke({"messages": [("user", "hi")]}, context={"identity": "demo"}))
    assert out["messages"][-1].content == "ok"
