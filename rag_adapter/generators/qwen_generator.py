import json

import httpx

from rag_adapter.models import Answer


class QwenGenerator:
    """以 OpenAI 相容的 /chat/completions API 生成答案(Qwen 模型)。

    generate 為一次性;stream 解析 SSE 逐段回傳。citations 由呼叫端帶入、原樣附回。
    """

    def __init__(self, base_url, api_key, model, client=None, system_prompt="", temperature=0.0):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=120)
        self._system_prompt = system_prompt
        self._temperature = temperature

    def _messages(self, prompt):
        messages = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _headers(self):
        return {"Authorization": f"Bearer {self._api_key}"}

    def _payload(self, prompt, stream):
        return {
            "model": self._model,
            "messages": self._messages(prompt),
            "temperature": self._temperature,
            "stream": stream,
        }

    async def generate(self, prompt, citations):
        response = await self._client.post(
            f"{self._base_url}/chat/completions",
            headers=self._headers(),
            json=self._payload(prompt, False),
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"]
        return Answer(text=text, citations=list(citations))

    async def stream(self, prompt, citations):
        async with self._client.stream(
            "POST",
            f"{self._base_url}/chat/completions",
            headers=self._headers(),
            json=self._payload(prompt, True),
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                delta = json.loads(data)["choices"][0].get("delta", {})
                content = delta.get("content")
                if content:
                    yield content
