import asyncio

import httpx
import pytest

from agent_template.a2a.card import CardSpec
from agent_template.a2a.server import build_a2a_app, build_agent_card
from agent_template.config import ConfigError
from agent_template.core.agent import Agent

from a2a.client import A2ACardResolver, ClientFactory
from a2a.client.client import ClientConfig
from a2a.helpers.proto_helpers import new_text_message
from a2a.types import Role, SendMessageRequest


class StubAgent:
    """最小 astream 介面:executor 只吃這個。"""

    def __init__(self, chunks=None, error=None):
        self.chunks = chunks or ["hel", "lo"]
        self.error = error
        self.asked = None

    async def astream(self, text):
        self.asked = text
        if self.error:
            raise self.error
        for chunk in self.chunks:
            yield chunk


def make_spec(**kw):
    return CardSpec(name="test-agent", description="a test agent", **kw)


async def roundtrip(app, text, base_url="http://testserver"):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=base_url) as hc:
        card = await A2ACardResolver(httpx_client=hc, base_url=base_url).get_agent_card()
        client = ClientFactory(ClientConfig(httpx_client=hc)).create(card)
        try:
            request = SendMessageRequest(message=new_text_message(text=text, role=Role.ROLE_USER))
            final, events = None, []
            async for response in client.send_message(request):
                for field in ("task", "message", "status_update", "artifact_update"):
                    if response.HasField(field):
                        events.append(field)
                        break
                if response.HasField("artifact_update"):
                    texts = [
                        part.text
                        for part in response.artifact_update.artifact.parts
                        if part.HasField("text")
                    ]
                    if texts:
                        final = "".join(texts)
            return final, events
        finally:
            await client.close()


def test_card_endpoint_serves_spec_fields():
    app = build_a2a_app(StubAgent(), make_spec(version="2.0.0"), host="0.0.0.0", port=9000)

    async def fetch():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as hc:
            return (await hc.get("/.well-known/agent-card.json")).json()

    card = asyncio.run(fetch())
    assert card["name"] == "test-agent"
    assert card["version"] == "2.0.0"
    assert card["capabilities"]["streaming"] is True


def test_default_url_from_host_port():
    card = build_agent_card(make_spec(), "0.0.0.0", 9000)
    assert card.supported_interfaces[0].url == "http://0.0.0.0:9000"
    card2 = build_agent_card(make_spec(url="https://public.example"), "0.0.0.0", 9000)
    assert card2.supported_interfaces[0].url == "https://public.example"


def test_default_chat_skill():
    card = build_agent_card(make_spec(), "h", 1)
    assert [s.id for s in card.skills] == ["chat"]


def test_send_message_roundtrip():
    stub = StubAgent()
    app = build_a2a_app(stub, make_spec())
    final, _ = asyncio.run(roundtrip(app, "what time is it"))
    assert final == "hello"
    assert stub.asked == "what time is it"


def test_streaming_chunks_arrive_incrementally():
    app = build_a2a_app(StubAgent(chunks=["a", "b", "c"]), make_spec())

    async def collect():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as hc:
            card = await A2ACardResolver(httpx_client=hc, base_url="http://t").get_agent_card()
            client = ClientFactory(ClientConfig(httpx_client=hc)).create(card)
            try:
                request = SendMessageRequest(
                    message=new_text_message(text="hi", role=Role.ROLE_USER)
                )
                chunks = []
                async for response in client.send_message(request):
                    if response.HasField("status_update"):
                        status = response.status_update.status
                        if status.HasField("message"):
                            chunks += [
                                p.text for p in status.message.parts
                                if p.HasField("text") and p.text
                            ]
                return chunks
            finally:
                await client.close()

    assert asyncio.run(collect()) == ["a", "b", "c"]  # stream_a2a 依賴的事件契約


def test_agent_error_fails_task():
    app = build_a2a_app(StubAgent(error=RuntimeError("model down")), make_spec())
    final, _ = asyncio.run(roundtrip(app, "hi"))
    assert final is None  # 沒有 artifact,task 進 failed


def test_auth_shell_rejects():
    async def deny(context):
        return False

    app = build_a2a_app(StubAgent(), make_spec(), auth=deny)
    final, _ = asyncio.run(roundtrip(app, "hi"))
    assert final is None  # 被 reject,拿不到 answer artifact


def test_agent_a2a_app_requires_card():
    agent = Agent(native=object())  # 沒 card
    with pytest.raises(ConfigError, match="agent card"):
        agent.a2a_app()


def test_agent_a2a_app_with_card():
    agent = Agent(native=object(), card=make_spec())
    app = agent.a2a_app()
    assert app is not None
