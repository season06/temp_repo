from __future__ import annotations

from src.rag_adapter.core.types import Citation, RagContext, RetrievedChunk


class SimpleContextBuilder:
    async def build(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        max_tokens: int,
    ) -> RagContext:
        selected: list[RetrievedChunk] = []
        citations: list[Citation] = []
        parts: list[str] = []
        token_count = 0

        for index, chunk in enumerate(chunks, start=1):
            chunk_tokens = self._estimate_tokens(chunk.text)
            if selected and token_count + chunk_tokens > max_tokens:
                break
            token_count += chunk_tokens
            selected.append(chunk)
            citations.append(
                Citation(
                    source_uri=str(chunk.metadata.get("source_uri", "")),
                    title=chunk.metadata.get("title"),
                    section=chunk.metadata.get("section_path"),
                    page_number=chunk.metadata.get("page_number"),
                    chunk_id=chunk.id,
                )
            )
            parts.append(f"[{index}] {chunk.text}")

        return RagContext(
            text="\n\n".join(parts),
            chunks=selected,
            citations=citations,
            token_count=token_count,
        )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text) // 4)

