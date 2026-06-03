from __future__ import annotations

import re

from src.rag_adapter.core.types import ParsedDocument, ParsedSection, RawDocument


class TextParser:
    async def parse(self, document: RawDocument) -> ParsedDocument:
        text = document.content.decode("utf-8") if isinstance(document.content, bytes) else document.content
        normalized = re.sub(r"\n{3,}", "\n\n", text.strip())
        title = self._extract_title(normalized)
        return ParsedDocument(
            id=document.id,
            source_uri=document.source_uri,
            text=normalized,
            title=title,
            sections=[ParsedSection(title=title, text=normalized, level=1, metadata={})],
            metadata=document.metadata,
        )

    @staticmethod
    def _extract_title(text: str) -> str | None:
        for line in text.splitlines():
            clean = line.strip().lstrip("#").strip()
            if clean:
                return clean[:160]
        return None

