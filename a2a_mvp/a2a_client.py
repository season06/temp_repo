import httpx
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory, create_text_message_object


class RemoteNotAllowed(Exception):
    pass


def _check_allowed(base_url, config):
    if not any(base_url.startswith(a) for a in config.allowed_remote_agents):
        raise RemoteNotAllowed(base_url)


async def call_peer(base_url, prompt, config):
    _check_allowed(base_url, config)
    headers = {}
    if config.outbound_service_token:
        headers["Authorization"] = f"Bearer {config.outbound_service_token}"
    async with httpx.AsyncClient(headers=headers, timeout=30) as http:
        resolver = A2ACardResolver(httpx_client=http, base_url=base_url)
        card = await resolver.get_agent_card()
        factory = ClientFactory(ClientConfig(streaming=False, httpx_client=http))
        client = factory.create(card)
        message = create_text_message_object(content=prompt)
        chunks = []
        async for event in client.send_message(message):
            chunks.append(str(event))
        return "\n".join(chunks)
