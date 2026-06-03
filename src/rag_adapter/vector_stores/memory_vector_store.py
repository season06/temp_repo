from __future__ import annotations

import math

from src.rag_adapter.core.types import EmbeddedChunk, RetrievalRequest, RetrievedChunk


class MemoryVectorStore:
    def __init__(self) -> None:
        self._chunks: dict[str, EmbeddedChunk] = {}

    async def upsert(self, chunks: list[EmbeddedChunk]) -> None:
        for chunk in chunks:
            self._chunks[chunk.id] = chunk

    async def query(self, request: RetrievalRequest, query_embedding: list[float]) -> list[RetrievedChunk]:
        results: list[RetrievedChunk] = []
        for chunk in self._chunks.values():
            if request.tenant_id and chunk.metadata.get("tenant_id") != request.tenant_id:
                continue
            if not self._matches_filters(chunk, request.filters):
                continue
            score = self._cosine_similarity(query_embedding, chunk.embedding)
            if request.score_threshold is not None and score < request.score_threshold:
                continue
            results.append(
                RetrievedChunk(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    text=chunk.text,
                    metadata=chunk.metadata,
                    score=score,
                )
            )
        results.sort(key=lambda item: item.score, reverse=True)
        return results[: request.top_k]

    async def delete(self, filters: dict[str, object]) -> None:
        chunk_ids = [
            chunk_id
            for chunk_id, chunk in self._chunks.items()
            if self._matches_filters(chunk, filters)
        ]
        for chunk_id in chunk_ids:
            del self._chunks[chunk_id]

    @staticmethod
    def _matches_filters(chunk: EmbeddedChunk, filters: dict[str, object]) -> bool:
        return all(chunk.metadata.get(key) == value for key, value in filters.items())

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            return 0.0
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)

