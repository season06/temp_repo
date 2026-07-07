"""以 peer 身分呼叫本機 server:自簽 HS256 JWT → A2A client 送 message/send。"""
import asyncio
import time
import jwt
import httpx
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory, create_text_message_object

BASE = "http://127.0.0.1:9999"


def mint():
    return jwt.encode({"sub": "peer-cli", "iss": "https://issuer.local",
                       "aud": "a2a-mvp", "exp": int(time.time()) + 300},
                      "s", algorithm="HS256")


async def main():
    headers = {"Authorization": f"Bearer {mint()}"}
    async with httpx.AsyncClient(headers=headers, timeout=30) as http:
        card = await A2ACardResolver(httpx_client=http, base_url=BASE).get_agent_card()
        client = ClientFactory(ClientConfig(streaming=False, httpx_client=http)).create(card)
        async for event in client.send_message(create_text_message_object(content="用一句話自我介紹")):
            print(event)


if __name__ == "__main__":
    asyncio.run(main())
