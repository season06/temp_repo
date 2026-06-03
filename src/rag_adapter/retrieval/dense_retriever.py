from __future__ import annotations

from src.rag_adapter.core.types import Embedder, RetrievalRequest, RetrievedChunk, VectorStore


class DenseRetriever:
    def __init__(self, embedder: Embedder, vector_store: VectorStore) -> None:
        self.embedder = embedder
        self.vector_store = vector_store

    async def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        query_embedding = await self.embedder.embed_query(request.query)
        return await self.vector_store.query(request, query_embedding)

