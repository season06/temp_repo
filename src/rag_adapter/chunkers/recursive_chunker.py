from __future__ import annotations

import hashlib
from dataclasses import dataclass

from src.rag_adapter.core.types import Chunk, ParsedDocument


@dataclass(frozen=True)
class RecursiveChunker:
    chunk_size: int = 900
    chunk_overlap: int = 120

    async def chunk(self, document: ParsedDocument) -> list[Chunk]:
        if not document.text:
            return []

        chunks: list[Chunk] = []
        start = 0
        text = document.text
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            if end < len(text):
                boundary = max(text.rfind("\n\n", start, end), text.rfind(". ", start, end))
                if boundary > start + self.chunk_size // 2:
                    end = boundary + 1

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunk_id = self._chunk_id(document.id, start, chunk_text)
                metadata = {
                    **document.metadata,
                    "source_uri": document.source_uri,
                    "title": document.title,
                    "start_offset": start,
                    "end_offset": end,
                }
                chunks.append(
                    Chunk(
                        id=chunk_id,
                        document_id=document.id,
                        text=chunk_text,
                        metadata=metadata,
                    )
                )

            if end >= len(text):
                break
            start = max(end - self.chunk_overlap, start + 1)
        return chunks

    @staticmethod
    def _chunk_id(document_id: str, start: int, text: str) -> str:
        digest = hashlib.sha256(f"{document_id}:{start}:{text}".encode("utf-8")).hexdigest()
        return digest[:24]

