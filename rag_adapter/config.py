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
class RetrieverConfig:
    type: str = "dense"
    top_k: int = 20

    def __post_init__(self) -> None:
        if self.top_k <= 0:
            raise ValueError("top_k must be greater than 0")


@dataclass(frozen=True)
class FusionConfig:
    type: str = "rrf"
    k: int = 60


@dataclass(frozen=True)
class RerankerConfig:
    type: str = "qwen"
    base_url: str = ""
    api_key: str = ""
    model: str = "qwen-reranker"


@dataclass(frozen=True)
class ContextConfig:
    max_chars: int = 6000

    def __post_init__(self) -> None:
        if self.max_chars <= 0:
            raise ValueError("max_chars must be greater than 0")


@dataclass(frozen=True)
class PromptBuilderConfig:
    type: str = "template"
    template: str | None = None


@dataclass(frozen=True)
class GeneratorConfig:
    type: str = "qwen"
    base_url: str = ""
    api_key: str = ""
    model: str = "qwen-max"
    temperature: float = 0.0
    system_prompt: str = ""


@dataclass(frozen=True)
class GenerationConfig:
    enabled: bool = False
    prompt_builder: PromptBuilderConfig = field(default_factory=PromptBuilderConfig)
    generator: GeneratorConfig = field(default_factory=GeneratorConfig)


@dataclass(frozen=True)
class QueryConfig:
    retriever: RetrieverConfig = field(default_factory=RetrieverConfig)
    fusion: FusionConfig = field(default_factory=FusionConfig)
    reranker: RerankerConfig = field(default_factory=RerankerConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    top_k: int = 8

    def __post_init__(self) -> None:
        if self.top_k <= 0:
            raise ValueError("top_k must be greater than 0")


@dataclass(frozen=True)
class EvaluationConfig:
    enabled: bool = False
    metrics: list = field(default_factory=lambda: [
        "faithfulness", "answer_relevancy", "context_precision", "context_recall",
    ])
    judge_base_url: str = ""
    judge_api_key: str = ""
    judge_model: str = "qwen-max"
    embedding_model: str = "qwen-embedding"


@dataclass(frozen=True)
class RagConfig:
    indexing: IndexingConfig = field(default_factory=IndexingConfig)
    query: QueryConfig = field(default_factory=QueryConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)


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


def _generation_from_dict(raw: dict) -> GenerationConfig:
    return GenerationConfig(
        enabled=raw.get("enabled", False),
        prompt_builder=PromptBuilderConfig(**raw.get("prompt_builder", {})),
        generator=GeneratorConfig(**raw.get("generator", {})),
    )


def _query_from_dict(raw: dict) -> QueryConfig:
    return QueryConfig(
        retriever=RetrieverConfig(**raw.get("retriever", {})),
        fusion=FusionConfig(**raw.get("fusion", {})),
        reranker=RerankerConfig(**raw.get("reranker", {})),
        context=ContextConfig(**raw.get("context", {})),
        generation=_generation_from_dict(raw.get("generation", {})),
        top_k=raw.get("top_k", 8),
    )


def _evaluation_from_dict(raw: dict) -> EvaluationConfig:
    return EvaluationConfig(**raw)


def from_dict(raw: dict) -> RagConfig:
    """把已插值的 dict 轉成 typed RagConfig。"""
    return RagConfig(
        indexing=_indexing_from_dict(raw.get("indexing", {})),
        query=_query_from_dict(raw.get("query", {})),
        evaluation=_evaluation_from_dict(raw.get("evaluation", {})),
    )


def load_config(path: str) -> RagConfig:
    """讀取 YAML 配置,把 ${ENV:VAR} 以環境變數插值,回傳 typed RagConfig。"""
    with open(path, encoding="utf-8") as handle:
        raw = _interpolate(yaml.safe_load(handle) or {})
    return from_dict(raw)
