import httpx

from rag_adapter.models import RetrievedChunk


class QwenReranker:
    """以 Qwen reranker API 對候選重排;回傳 top_k,score 改為 relevance score。"""

    def __init__(self, base_url, api_key, model, client=None):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=60)

    async def rerank(self, query, candidates, top_k):
        if not candidates:
            return []
        documents = [rc.chunk.text for rc in candidates]
        response = await self._client.post(
            f"{self._base_url}/rerank",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self._model, "query": query, "documents": documents, "top_n": top_k},
        )
        response.raise_for_status()
        reranked = []
        for item in response.json()["results"]:
            candidate = candidates[item["index"]]
            reranked.append(RetrievedChunk(chunk=candidate.chunk, score=item["relevance_score"]))
        return reranked
