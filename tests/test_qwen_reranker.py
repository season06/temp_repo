from rag_adapter.models import Chunk, RetrievedChunk
from rag_adapter.rerankers.qwen_reranker import QwenReranker


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeHttpClient:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    async def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return FakeResponse(self._payload)


def _rc(cid, text):
    return RetrievedChunk(chunk=Chunk(id=cid, document_id="d", text=text), score=0.0)


async def test_reranker_reorders_by_relevance():
    candidates = [_rc("c1", "alpha"), _rc("c2", "beta"), _rc("c3", "gamma")]
    payload = {"results": [
        {"index": 2, "relevance_score": 0.9},
        {"index": 0, "relevance_score": 0.4},
    ]}
    client = FakeHttpClient(payload)
    reranker = QwenReranker(base_url="https://api/v1/", api_key="k", model="qwen-reranker", client=client)

    results = await reranker.rerank("q", candidates, top_k=2)

    assert [rc.chunk.id for rc in results] == ["c3", "c1"]
    assert results[0].score == 0.9
    assert client.calls[0]["url"] == "https://api/v1/rerank"
    assert client.calls[0]["headers"]["Authorization"] == "Bearer k"
    assert client.calls[0]["json"]["top_n"] == 2
    assert client.calls[0]["json"]["documents"] == ["alpha", "beta", "gamma"]


async def test_reranker_empty_candidates():
    client = FakeHttpClient({"results": []})
    reranker = QwenReranker(base_url="https://api/v1", api_key="k", model="m", client=client)

    assert await reranker.rerank("q", [], top_k=3) == []
    assert client.calls == []
