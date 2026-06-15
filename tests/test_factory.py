import textwrap

import pytest

from rag_adapter.config import load_config, LoaderConfig
from rag_adapter.factory import build_indexing_pipeline, _build_loader
from rag_adapter.loaders.file_loader import FileLoader
from rag_adapter.parsers.html_parser import HtmlParser
from rag_adapter.chunkers.character_chunker import CharacterChunker
from rag_adapter.embedders.qwen_embedder import QwenEmbedder
from rag_adapter.vectorstores.qdrant_store import QdrantVectorStore


_YAML = """
indexing:
  loader:
    type: file
    loader_name: html
  parser:
    type: html
  chunker:
    type: character
    chunk_size: 500
    chunk_overlap: 50
  embedder:
    type: qwen
    base_url: https://api/v1
    api_key: ${ENV:QWEN_KEY}
    model: text-embedding-v3
  vector_store:
    type: qdrant
    url: http://localhost:6333
    collection: docs
"""


def test_build_indexing_pipeline_from_config(tmp_path, monkeypatch):
    monkeypatch.setenv("QWEN_KEY", "secret-123")
    cfg = tmp_path / "rag.yaml"
    cfg.write_text(textwrap.dedent(_YAML), encoding="utf-8")
    config = load_config(str(cfg))

    pipeline = build_indexing_pipeline(config)

    assert isinstance(pipeline._loader, FileLoader)
    assert isinstance(pipeline._parser, HtmlParser)
    assert isinstance(pipeline._chunker, CharacterChunker)
    assert isinstance(pipeline._embedder, QwenEmbedder)
    assert isinstance(pipeline._vector_store, QdrantVectorStore)
    assert pipeline._embedder._api_key == "secret-123"
    assert pipeline._chunker._chunk_size == 500
    assert pipeline._vector_store._collection == "docs"


def test_unknown_loader_type_raises():
    with pytest.raises(ValueError):
        _build_loader(LoaderConfig(type="ftp"))
