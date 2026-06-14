from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChunkerConfig:
    chunk_size: int = 900
    chunk_overlap: int = 120
    preserve_headings: bool = True

    def __post_init__(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap must be greater than or equal to 0")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")


@dataclass(frozen=True)
class EmbedderConfig:
    provider: str = "qwen"
    model: str = "qwen-embedding"
    dimension: int = 4096
    endpoint_url: str | None = None
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.provider == "qwen" and self.dimension != 4096:
            raise ValueError("Qwen embedding dimension must be 4096")


@dataclass(frozen=True)
class RetrieverConfig:
    top_k: int = 20
    score_threshold: float | None = None

    def __post_init__(self) -> None:
        if self.top_k <= 0:
            raise ValueError("top_k must be greater than 0")


@dataclass(frozen=True)
class RerankerConfig:
    provider: str = "qwen"
    model: str = "qwen-reranker"
    endpoint_url: str | None = None
    top_n: int = 8

    def __post_init__(self) -> None:
        if self.top_n <= 0:
            raise ValueError("top_n must be greater than 0")


@dataclass(frozen=True)
class ContextConfig:
    max_tokens: int = 6000

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be greater than 0")


@dataclass(frozen=True)
class RagConfig:
    tenant_id: str = "default"
    chunker: ChunkerConfig = field(default_factory=ChunkerConfig)
    embedder: EmbedderConfig = field(default_factory=EmbedderConfig)
    retriever: RetrieverConfig = field(default_factory=RetrieverConfig)
    reranker: RerankerConfig = field(default_factory=RerankerConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
