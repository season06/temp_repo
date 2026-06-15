from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import yaml


@dataclass(frozen=True)
class LoaderConfig:
    type: str = "file"
    loader_name: str = "file"
    base_url: str | None = None

    def __post_init__(self) -> None:
        if self.type == "tkms" and not self.base_url:
            raise ValueError("tkms loader requires base_url")


@dataclass(frozen=True)
class ParserConfig:
    type: str = "html"


@dataclass(frozen=True)
class ChunkerConfig:
    type: str = "character"
    chunk_size: int = 800
    chunk_overlap: int = 100

    def __post_init__(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap must be greater than or equal to 0")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")


@dataclass(frozen=True)
class EmbedderConfig:
    type: str = "qwen"
    base_url: str = ""
    api_key: str = ""
    model: str = "qwen-embedding"
    batch_size: int = 16

    def __post_init__(self) -> None:
        if self.batch_size <= 0:
            raise ValueError("batch_size must be greater than 0")


@dataclass(frozen=True)
class VectorStoreConfig:
    type: str = "qdrant"
    url: str = "http://localhost:6333"
    collection: str = "documents"


@dataclass(frozen=True)
class IndexingConfig:
    loader: LoaderConfig = field(default_factory=LoaderConfig)
    parser: ParserConfig = field(default_factory=ParserConfig)
    chunker: ChunkerConfig = field(default_factory=ChunkerConfig)
    embedder: EmbedderConfig = field(default_factory=EmbedderConfig)
    vector_store: VectorStoreConfig = field(default_factory=VectorStoreConfig)


@dataclass(frozen=True)
class RagConfig:
    indexing: IndexingConfig = field(default_factory=IndexingConfig)


_ENV_PATTERN = re.compile(r"\$\{ENV:([^}]+)\}")


def _interpolate(value):
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: os.environ[m.group(1)], value)
    if isinstance(value, dict):
        return {key: _interpolate(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_interpolate(item) for item in value]
    return value


def _indexing_from_dict(raw: dict) -> IndexingConfig:
    return IndexingConfig(
        loader=LoaderConfig(**raw.get("loader", {})),
        parser=ParserConfig(**raw.get("parser", {})),
        chunker=ChunkerConfig(**raw.get("chunker", {})),
        embedder=EmbedderConfig(**raw.get("embedder", {})),
        vector_store=VectorStoreConfig(**raw.get("vector_store", {})),
    )


def from_dict(raw: dict) -> RagConfig:
    """把已插值的 dict 轉成 typed RagConfig。"""
    return RagConfig(indexing=_indexing_from_dict(raw.get("indexing", {})))


def load_config(path: str) -> RagConfig:
    """讀取 YAML 配置,把 ${ENV:VAR} 以環境變數插值,回傳 typed RagConfig。"""
    with open(path, encoding="utf-8") as handle:
        raw = _interpolate(yaml.safe_load(handle) or {})
    return from_dict(raw)
