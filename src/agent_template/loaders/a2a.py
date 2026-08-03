"""A2A client 載入:把 config 宣告的遠端 agent 包成 langchain tool。

build 時一律抓 Agent Card(description 給 LLM 看);抓不到 → warning + 跳過。
call_a2a 為公開 helper,headers 留 auth 殼(預設 None)。
"""

import logging
import warnings

import httpx
from langchain_core.tools import StructuredTool

from a2a.client import A2ACardResolver, ClientFactory
from a2a.client.client import ClientConfig
from a2a.helpers.proto_helpers import get_message_text, new_text_message
from a2a.types import Role, SendMessageRequest

from ..utils._async import run_sync

logger = logging.getLogger("agent_template")


def load_a2a_tools(agents: list) -> list:
    tools = []
    for agent in agents:
        try:
            card = run_sync(_fetch_card(agent.url))
        except Exception as exc:
            warnings.warn(f"A2A agent '{agent.name}' 的 card 抓取失敗,已跳過: {exc}")
            continue
        tools.append(_make_tool(agent, card))
    logger.info("load_a2a_tools: 載入 %d 個 a2a tool", len(tools))
    return tools


async def call_a2a(url, text, headers: dict = None):
    """送一則文字訊息給遠端 A2A agent,回最終回應文字(無則 None)。"""
    async with httpx.AsyncClient(headers=headers, timeout=60) as http_client:
        card = await A2ACardResolver(httpx_client=http_client, base_url=url).get_agent_card()
        client = ClientFactory(ClientConfig(httpx_client=http_client)).create(card)
        try:
            request = SendMessageRequest(
                message=new_text_message(text=text, role=Role.ROLE_USER)
            )
            final = None
            async for response in client.send_message(request):
                if response.HasField("message"):
                    final = get_message_text(response.message)
                elif response.HasField("artifact_update"):
                    texts = [
                        part.text
                        for part in response.artifact_update.artifact.parts
                        if part.HasField("text")
                    ]
                    if texts:
                        final = "".join(texts)
            return final
        finally:
            await client.close()


async def stream_a2a(url, text, headers: dict = None):
    """同 call_a2a,但逐段吐遠端 agent 的文字 chunk(server 邊生成邊推)。"""
    async with httpx.AsyncClient(headers=headers, timeout=60) as http_client:
        card = await A2ACardResolver(httpx_client=http_client, base_url=url).get_agent_card()
        client = ClientFactory(ClientConfig(httpx_client=http_client)).create(card)
        try:
            request = SendMessageRequest(
                message=new_text_message(text=text, role=Role.ROLE_USER)
            )
            async for response in client.send_message(request):
                if response.HasField("message"):
                    yield get_message_text(response.message)
                elif response.HasField("status_update"):
                    status = response.status_update.status
                    if status.HasField("message"):
                        for part in status.message.parts:
                            if part.HasField("text") and part.text:
                                yield part.text
        finally:
            await client.close()


async def _fetch_card(url):
    async with httpx.AsyncClient(timeout=10) as http_client:
        return await A2ACardResolver(httpx_client=http_client, base_url=url).get_agent_card()


def _make_tool(agent, card):
    async def ask(query: str) -> str:
        answer = await call_a2a(agent.url, query)
        return answer or ""

    description = card.description or f"Remote agent '{card.name}'."
    return StructuredTool.from_function(
        coroutine=ask, name=agent.name, description=description
    )
