import textwrap

import pytest

from rag_adapter.config import load_config, from_dict, RagConfig, ChunkerConfig, LoaderConfig


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
query:
  retriever:
    type: dense
    top_k: 30
  fusion:
    type: rrf
    k: 40
  reranker:
    type: qwen
    base_url: https://api/v1
    api_key: ${ENV:QWEN_KEY}
    model: qwen-reranker
  context:
    max_chars: 1234
  top_k: 5
"""


def _write_cfg(tmp_path):
    cfg = tmp_path / "rag.yaml"
    cfg.write_text(textwrap.dedent(_YAML), encoding="utf-8")
    return str(cfg)


def test_load_config_returns_typed_config_with_env_interpolation(tmp_path, monkeypatch):
    monkeypatch.setenv("QWEN_KEY", "secret-123")

    config = load_config(_write_cfg(tmp_path))

    assert isinstance(config, RagConfig)
    assert config.indexing.embedder.api_key == "secret-123"
    assert config.indexing.chunker.chunk_size == 500
    assert config.indexing.vector_store.collection == "docs"
    assert config.indexing.loader.loader_name == "html"
    assert config.query.retriever.top_k == 30
    assert config.query.fusion.k == 40
    assert config.query.reranker.api_key == "secret-123"
    assert config.query.context.max_chars == 1234
    assert config.query.top_k == 5


def test_defaults_applied_when_sections_missing():
    config = from_dict({})

    assert config.indexing.chunker.type == "character"
    assert config.indexing.embedder.type == "qwen"
    assert config.indexing.vector_store.url == "http://localhost:6333"


def test_chunker_config_validates_overlap():
    with pytest.raises(ValueError):
        ChunkerConfig(chunk_size=10, chunk_overlap=10)


def test_tkms_loader_config_requires_base_url():
    with pytest.raises(ValueError):
        LoaderConfig(type="tkms")
