from __future__ import annotations

from src.rag_adapter.core.types import RetrievedChunk


class NoopReranker:
    model_name = "noop-reranker"

    async def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return chunks

