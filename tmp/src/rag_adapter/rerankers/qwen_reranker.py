from __future__ import annotations

from dataclasses import replace
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.rag_adapter.core.errors import ConfigurationError, ProviderError
from src.rag_adapter.core.types import RetrievedChunk


class QwenReranker:
    def __init__(
        self,
        endpoint_url: str,
        model_name: str = "qwen-reranker",
        timeout_seconds: float = 30.0,
    ) -> None:
        if not endpoint_url:
            raise ConfigurationError("Qwen reranker requires endpoint_url")
        self.endpoint_url = endpoint_url
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

    async def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not chunks:
            return []
        payload = {
            "model": self.model_name,
            "query": query,
            "documents": [{"id": chunk.id, "text": chunk.text} for chunk in chunks],
        }
        data = await self._post(payload)
        scores = {item["id"]: float(item["score"]) for item in data["results"]}
        reranked = [replace(chunk, rerank_score=scores.get(chunk.id, 0.0)) for chunk in chunks]
        reranked.sort(key=lambda item: item.rerank_score or 0.0, reverse=True)
        return reranked

    @retry(wait=wait_exponential(multiplier=0.5, min=0.5, max=4), stop=stop_after_attempt(3))
    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(self.endpoint_url, json=payload)
        if response.status_code >= 500:
            raise ProviderError(f"Qwen reranker provider failed: {response.status_code}")
        response.raise_for_status()
        return response.json()

