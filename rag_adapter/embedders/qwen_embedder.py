import httpx


class QwenEmbedder:
    """以 OpenAI 相容的 /embeddings API 非同步取得向量(Qwen 模型)。"""

    def __init__(self, base_url, api_key, model, client=None, batch_size=16):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=60)
        self._batch_size = batch_size

    async def embed(self, chunks):
        vectors = await self._embed_texts([c.text for c in chunks])
        for chunk, vector in zip(chunks, vectors):
            chunk.embedding = vector
        return chunks

    async def embed_query(self, text):
        vectors = await self._embed_texts([text])
        return vectors[0]

    async def _embed_texts(self, texts):
        vectors = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start:start + self._batch_size]
            response = await self._client.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "input": batch},
            )
            response.raise_for_status()
            vectors.extend(item["embedding"] for item in response.json()["data"])
        return vectors
