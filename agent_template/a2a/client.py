from __future__ import annotations

from typing import Any

from a2a.client import A2ACardResolver, ClientFactory
from a2a.client.client import ClientConfig
from a2a.helpers.proto_helpers import new_text_message, get_message_text
from a2a.types import Role, SendMessageRequest


async def call_agent(httpx_client: Any, base_url: str, text: str) -> str | None:
    """抓 base_url 的 Agent Card、建 A2A client、送 text,回最終回應文字(無則 None)。"""
    card = await A2ACardResolver(httpx_client=httpx_client, base_url=base_url).get_agent_card()
    client = ClientFactory(ClientConfig(httpx_client=httpx_client)).create(card)
    try:
        request = SendMessageRequest(message=new_text_message(text=text, role=Role.ROLE_USER))
        final_text = None
        async for response in client.send_message(request):
            if response.HasField("message"):
                final_text = get_message_text(response.message)
        return final_text
    finally:
        await client.close()
