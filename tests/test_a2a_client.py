import asyncio

import httpx
from langchain_core.messages import AIMessage
from deepagents import create_deep_agent

from agent_template.a2a import build_agent_card, build_a2a_app
from agent_template.a2a import call_agent
from tests.fakes import FakeToolModel

BASE = "http://test"


def _agent(reply):
    return create_deep_agent(model=FakeToolModel(scripted=[AIMessage(content=reply)]), tools=[], system_prompt="x")


def test_call_agent_end_to_end():
    app = build_a2a_app(_agent("pong from server"), build_agent_card(name="Svc", url=BASE + "/"))

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as hc:
            return await call_agent(hc, BASE, "ping")

    assert asyncio.run(go()) == "pong from server"
