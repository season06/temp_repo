from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from rag_adapter import RagAdapter
from rag_adapter.core.config import EmbedderConfig


def test_index_and_retrieve() -> None:
    workspace = Path("test_workspace")
    if workspace.exists():
        shutil.rmtree(workspace)
    try:
        asyncio.run(_index_and_retrieve(workspace))
    finally:
        if workspace.exists():
            shutil.rmtree(workspace)


async def _index_and_retrieve(workspace: Path) -> None:
    docs = workspace / "docs"
    docs.mkdir(parents=True)
    (docs / "rag.md").write_text(
        "# RAG Adapter\n\nQwen embedding uses 4096 dimensions.\n\nLangfuse records traces.",
        encoding="utf-8",
    )

    rag = RagAdapter()
    chunks = await rag.index({"type": "local_directory", "path": str(docs)}, tenant_id="tenant-a")
    results = await rag.retrieve("Qwen embedding dimensions", tenant_id="tenant-a", top_k=3)

    assert chunks
    assert results
    assert results[0].metadata["tenant_id"] == "tenant-a"
    assert "Qwen" in results[0].text


def test_qwen_dimension_validation() -> None:
    with pytest.raises(ValueError, match="Qwen embedding dimension must be 4096"):
        EmbedderConfig(provider="qwen", dimension=1024)
