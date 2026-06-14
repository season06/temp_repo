from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class RawDocument:
    id: str
    source_uri: str
    content: bytes | str
    metadata: dict[str, Any] = field(default_factory=dict)
    mime_type: str | None = None


@dataclass(frozen=True)
class ParsedSection:
    title: str | None
    text: str
    level: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedDocument:
    id: str
    source_uri: str
    text: str
    sections: list[ParsedSection]
    metadata: dict[str, Any] = field(default_factory=dict)
    title: str | None = None


@dataclass(frozen=True)
class Chunk:
    id: str
    document_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddedChunk(Chunk):
    embedding: list[float] = field(default_factory=list)
    embedding_model: str = ""
    embedding_dimension: int = 0


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    top_k: int = 10
    tenant_id: str | None = None
    filters: dict[str, Any] = field(default_factory=dict)
    score_threshold: float | None = None


@dataclass(frozen=True)
class RetrievedChunk(Chunk):
    score: float = 0.0
    rerank_score: float | None = None


@dataclass(frozen=True)
class Citation:
    source_uri: str
    title: str | None = None
    section: str | None = None
    page_number: int | None = None
    chunk_id: str | None = None


@dataclass(frozen=True)
class RagContext:
    text: str
    chunks: list[RetrievedChunk]
    citations: list[Citation]
    token_count: int


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    context: RagContext
    trace_id: str | None = None


class DocumentLoader(Protocol):
    async def load(self, source: dict[str, Any]) -> list[RawDocument]:
        ...


class DocumentParser(Protocol):
    async def parse(self, document: RawDocument) -> ParsedDocument:
        ...


class Chunker(Protocol):
    async def chunk(self, document: ParsedDocument) -> list[Chunk]:
        ...


class Embedder(Protocol):
    model_name: str
    dimension: int

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...

    async def embed_query(self, query: str) -> list[float]:
        ...


class VectorStore(Protocol):
    async def upsert(self, chunks: list[EmbeddedChunk]) -> None:
        ...

    async def query(self, request: RetrievalRequest, query_embedding: list[float]) -> list[RetrievedChunk]:
        ...

    async def delete(self, filters: dict[str, Any]) -> None:
        ...


class Retriever(Protocol):
    async def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        ...


class Reranker(Protocol):
    model_name: str

    async def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        ...


class ContextBuilder(Protocol):
    async def build(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        max_tokens: int,
    ) -> RagContext:
        ...

