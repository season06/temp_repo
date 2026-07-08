import asyncio

import httpx
from langchain_core.messages import AIMessage
from deepagents import create_deep_agent

from agent_template.a2a_server import build_agent_card, build_a2a_app
from tests.fakes import FakeToolModel

from a2a.client import A2ACardResolver, ClientFactory
from a2a.client.client import ClientConfig
from a2a.helpers.proto_helpers import new_text_message, get_message_text
from a2a.types import Role, SendMessageRequest

BASE = "http://test"


def _agent(reply):
    model = FakeToolModel(scripted=[AIMessage(content=reply)])
    return create_deep_agent(model=model, tools=[], system_prompt="x")


async def _roundtrip(app, text):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as hc:
        card = await A2ACardResolver(httpx_client=hc, base_url=BASE).get_agent_card()
        client = ClientFactory(ClientConfig(httpx_client=hc)).create(card)
        req = SendMessageRequest(message=new_text_message(text=text, role=Role.ROLE_USER))
        final = None
        async for r in client.send_message(req):
            if r.HasField("message"):
                final = get_message_text(r.message)
        await client.close()
        return final


class _Allow:
    async def verify(self, context):
        return True


class _Deny:
    async def verify(self, context):
        return False


def test_agent_card_has_interface_and_skill():
    card = build_agent_card(name="Svc", url=BASE + "/")
    assert card.name == "Svc"
    assert card.supported_interfaces[0].url == BASE + "/"
    assert len(card.skills) >= 1


def test_server_roundtrip_runs_our_agent():
    app = build_a2a_app(_agent("hi from agent"), build_agent_card(name="Svc", url=BASE + "/"))
    assert asyncio.run(_roundtrip(app, "hello")) == "hi from agent"


def test_inbound_auth_deny_returns_unauthorized_without_running_agent():
    app = build_a2a_app(_agent("secret"), build_agent_card(name="Svc", url=BASE + "/"), auth_client=_Deny())
    assert asyncio.run(_roundtrip(app, "hello")) == "unauthorized"


def test_inbound_auth_allow_runs_agent():
    app = build_a2a_app(_agent("allowed"), build_agent_card(name="Svc", url=BASE + "/"), auth_client=_Allow())
    assert asyncio.run(_roundtrip(app, "hello")) == "allowed"
