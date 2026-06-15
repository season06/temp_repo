class DenseRetriever:
    """以 embedder 將 query 轉向量,再用 vector store 做相似度檢索(cosine 由 store 設定)。"""

    def __init__(self, embedder, vector_store):
        self._embedder = embedder
        self._vector_store = vector_store

    async def retrieve(self, query, top_k):
        embedding = await self._embedder.embed_query(query)
        return await self._vector_store.search(embedding, top_k)
