from rag_adapter.models import Citation
from rag_adapter.generators.qwen_generator import QwenGenerator


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeStreamResponse:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class FakeStreamCtx:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *args):
        return False


class FakeHttpClient:
    def __init__(self, chat_payload=None, stream_lines=None):
        self._chat_payload = chat_payload
        self._stream_lines = stream_lines or []
        self.calls = []
        self.stream_calls = []

    async def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return FakeResponse(self._chat_payload)

    def stream(self, method, url, headers=None, json=None):
        self.stream_calls.append({"method": method, "url": url, "json": json})
        return FakeStreamCtx(FakeStreamResponse(self._stream_lines))


async def test_generate_returns_answer_with_citations():
    client = FakeHttpClient(chat_payload={"choices": [{"message": {"content": "the answer"}}]})
    gen = QwenGenerator(
        base_url="https://api/v1/",
        api_key="k",
        model="qwen-max",
        client=client,
        system_prompt="be helpful",
    )
    citations = [Citation(chunk_id="c1")]

    answer = await gen.generate("my prompt", citations)

    assert answer.text == "the answer"
    assert [c.chunk_id for c in answer.citations] == ["c1"]
    sent = client.calls[0]
    assert sent["url"] == "https://api/v1/chat/completions"
    assert sent["headers"]["Authorization"] == "Bearer k"
    assert sent["json"]["messages"][0] == {"role": "system", "content": "be helpful"}
    assert sent["json"]["messages"][1] == {"role": "user", "content": "my prompt"}
    assert sent["json"]["stream"] is False


async def test_generate_without_system_prompt_omits_system_message():
    client = FakeHttpClient(chat_payload={"choices": [{"message": {"content": "a"}}]})
    gen = QwenGenerator(base_url="https://api/v1", api_key="k", model="m", client=client)

    await gen.generate("p", [])

    messages = client.calls[0]["json"]["messages"]
    assert messages == [{"role": "user", "content": "p"}]


async def test_stream_yields_content_deltas():
    lines = [
        'data: {"choices": [{"delta": {"content": "Hel"}}]}',
        "",
        'data: {"choices": [{"delta": {"content": "lo"}}]}',
        "data: [DONE]",
    ]
    client = FakeHttpClient(stream_lines=lines)
    gen = QwenGenerator(base_url="https://api/v1", api_key="k", model="m", client=client)

    tokens = [token async for token in gen.stream("p", [])]

    assert tokens == ["Hel", "lo"]
    assert client.stream_calls[0]["json"]["stream"] is True
