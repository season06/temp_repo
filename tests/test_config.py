import textwrap

from rag_adapter.config import load_config, build_indexing_pipeline
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


def _write_cfg(tmp_path):
    cfg = tmp_path / "rag.yaml"
    cfg.write_text(textwrap.dedent(_YAML), encoding="utf-8")
    return str(cfg)


def test_load_config_interpolates_env(tmp_path, monkeypatch):
    monkeypatch.setenv("QWEN_KEY", "secret-123")

    config = load_config(_write_cfg(tmp_path))

    assert config["indexing"]["embedder"]["api_key"] == "secret-123"


def test_build_indexing_pipeline_from_config(tmp_path, monkeypatch):
    monkeypatch.setenv("QWEN_KEY", "secret-123")
    config = load_config(_write_cfg(tmp_path))

    pipeline = build_indexing_pipeline(config)

    assert isinstance(pipeline._loader, FileLoader)
    assert isinstance(pipeline._parser, HtmlParser)
    assert isinstance(pipeline._chunker, CharacterChunker)
    assert isinstance(pipeline._embedder, QwenEmbedder)
    assert isinstance(pipeline._vector_store, QdrantVectorStore)
    assert pipeline._embedder._api_key == "secret-123"
    assert pipeline._chunker._chunk_size == 500
    assert pipeline._vector_store._collection == "docs"
