from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.rag_adapter.core.errors import ConfigurationError, ProviderError


class QwenEmbedder:
    dimension = 4096

    def __init__(
        self,
        endpoint_url: str,
        model_name: str = "qwen-embedding",
        timeout_seconds: float = 30.0,
    ) -> None:
        if not endpoint_url:
            raise ConfigurationError("Qwen embedder requires endpoint_url")
        self.endpoint_url = endpoint_url
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {"model": self.model_name, "input": texts}
        data = await self._post(payload)
        embeddings = [item["embedding"] for item in data["data"]]
        for embedding in embeddings:
            if len(embedding) != self.dimension:
                raise ProviderError(f"Expected Qwen embedding dimension 4096, got {len(embedding)}")
        return embeddings

    async def embed_query(self, query: str) -> list[float]:
        return (await self.embed_texts([query]))[0]

    @retry(wait=wait_exponential(multiplier=0.5, min=0.5, max=4), stop=stop_after_attempt(3))
    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(self.endpoint_url, json=payload)
        if response.status_code >= 500:
            raise ProviderError(f"Qwen embedding provider failed: {response.status_code}")
        response.raise_for_status()
        return response.json()

