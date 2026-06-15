from rag_adapter.models import Chunk
from rag_adapter.embedders.qwen_embedder import QwenEmbedder


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeHttpClient:
    def __init__(self, batches):
        self._batches = list(batches)
        self.calls = []

    async def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        vectors = self._batches.pop(0)
        return FakeResponse({"data": [{"embedding": v} for v in vectors]})


async def test_embed_fills_embeddings_and_batches():
    client = FakeHttpClient(batches=[[[1.0], [2.0]], [[3.0]]])
    embedder = QwenEmbedder(
        base_url="https://api/v1/",
        api_key="k",
        model="text-embedding-v3",
        client=client,
        batch_size=2,
    )
    chunks = [
        Chunk(id="c1", document_id="d", text="a"),
        Chunk(id="c2", document_id="d", text="b"),
        Chunk(id="c3", document_id="d", text="c"),
    ]

    out = await embedder.embed(chunks)

    assert [c.embedding for c in out] == [[1.0], [2.0], [3.0]]
    assert len(client.calls) == 2
    assert client.calls[0]["url"] == "https://api/v1/embeddings"
    assert client.calls[0]["headers"]["Authorization"] == "Bearer k"
    assert client.calls[0]["json"] == {"model": "text-embedding-v3", "input": ["a", "b"]}


async def test_embed_query_returns_single_vector():
    client = FakeHttpClient(batches=[[[9.0]]])
    embedder = QwenEmbedder(
        base_url="https://api/v1",
        api_key="k",
        model="m",
        client=client,
    )

    assert await embedder.embed_query("hello") == [9.0]
