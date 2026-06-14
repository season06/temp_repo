from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from src.rag_adapter.core.types import RawDocument


class LocalDirectoryLoader:
    def __init__(self, default_encoding: str = "utf-8") -> None:
        self.default_encoding = default_encoding

    async def load(self, source: dict[str, Any]) -> list[RawDocument]:
        root = Path(str(source["path"])).expanduser().resolve()
        include_suffixes = set(source.get("suffixes", [".md", ".txt"]))
        tenant_id = source.get("tenant_id")

        documents: list[RawDocument] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in include_suffixes:
                continue
            content = path.read_text(encoding=self.default_encoding)
            digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
            metadata = {
                "source_path": str(path),
                "file_name": path.name,
                "suffix": path.suffix.lower(),
            }
            if tenant_id:
                metadata["tenant_id"] = tenant_id
            documents.append(
                RawDocument(
                    id=digest,
                    source_uri=path.as_uri(),
                    content=content,
                    metadata=metadata,
                    mime_type=self._mime_type(path),
                )
            )
        return documents

    @staticmethod
    def _mime_type(path: Path) -> str:
        if path.suffix.lower() == ".md":
            return "text/markdown"
        return "text/plain"

