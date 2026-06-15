import os
import re

import yaml

from rag_adapter.loaders.file_loader import FileLoader
from rag_adapter.loaders.http_loaders import UrlLoader, TkmsLoader
from rag_adapter.parsers.html_parser import HtmlParser
from rag_adapter.parsers.structured_parsers import JsonParser, XmlParser
from rag_adapter.chunkers.character_chunker import CharacterChunker
from rag_adapter.embedders.qwen_embedder import QwenEmbedder
from rag_adapter.vectorstores.qdrant_store import QdrantVectorStore
from rag_adapter.pipeline.indexing import IndexingPipeline


_ENV_PATTERN = re.compile(r"\$\{ENV:([^}]+)\}")


def _interpolate(value):
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: os.environ[m.group(1)], value)
    if isinstance(value, dict):
        return {key: _interpolate(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_interpolate(item) for item in value]
    return value


def load_config(path):
    """讀取 YAML 配置,並把 ${ENV:VAR} 以環境變數插值。"""
    with open(path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return _interpolate(raw)


def _build_loader(spec):
    spec = dict(spec)
    kind = spec.pop("type")
    if kind == "file":
        return FileLoader(**spec)
    if kind == "url":
        return UrlLoader(**spec)
    if kind == "tkms":
        return TkmsLoader(**spec)
    raise ValueError(f"unknown loader type: {kind}")


def _build_parser(spec):
    kind = spec["type"]
    if kind == "html":
        return HtmlParser()
    if kind == "json":
        return JsonParser()
    if kind == "xml":
        return XmlParser()
    raise ValueError(f"unknown parser type: {kind}")


def _build_chunker(spec):
    spec = dict(spec)
    kind = spec.pop("type")
    if kind == "character":
        return CharacterChunker(**spec)
    raise ValueError(f"unknown chunker type: {kind}")


def _build_embedder(spec):
    spec = dict(spec)
    kind = spec.pop("type")
    if kind == "qwen":
        return QwenEmbedder(**spec)
    raise ValueError(f"unknown embedder type: {kind}")


def _build_vector_store(spec):
    spec = dict(spec)
    kind = spec.pop("type")
    if kind == "qdrant":
        from qdrant_client import AsyncQdrantClient

        url = spec.pop("url")
        collection = spec.pop("collection")
        return QdrantVectorStore(client=AsyncQdrantClient(url=url), collection=collection)
    raise ValueError(f"unknown vector store type: {kind}")


def build_indexing_pipeline(config):
    """依 config 的 indexing 區塊組裝 IndexingPipeline。"""
    indexing = config["indexing"]
    return IndexingPipeline(
        loader=_build_loader(indexing["loader"]),
        parser=_build_parser(indexing["parser"]),
        chunker=_build_chunker(indexing["chunker"]),
        embedder=_build_embedder(indexing["embedder"]),
        vector_store=_build_vector_store(indexing["vector_store"]),
    )
