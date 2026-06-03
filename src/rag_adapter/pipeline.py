from __future__ import annotations

from dataclasses import replace
from typing import Any

from src.rag_adapter.chunkers.recursive_chunker import RecursiveChunker
from src.rag_adapter.context.context_builder import SimpleContextBuilder
from src.rag_adapter.core.config import RagConfig
from src.rag_adapter.core.types import (
    Chunk,
    ContextBuilder,
    DocumentLoader,
    DocumentParser,
    EmbeddedChunk,
    Embedder,
    RagAnswer,
    RetrievalRequest,
    Reranker,
    Retriever,
    VectorStore,
)
from src.rag_adapter.embedders.mock_embedder import MockEmbedder
from src.rag_adapter.loaders.local_directory_loader import LocalDirectoryLoader
from src.rag_adapter.observability.tracer import NullTracer
from src.rag_adapter.parsers.text_parser import TextParser
from src.rag_adapter.rerankers.noop_reranker import NoopReranker
from src.rag_adapter.retrieval.dense_retriever import DenseRetriever
from src.rag_adapter.vector_stores.memory_vector_store import MemoryVectorStore


class RagAdapter:
    def __init__(
        self,
        config: RagConfig | None = None,
        loader: DocumentLoader | None = None,
        parser: DocumentParser | None = None,
        chunker: RecursiveChunker | None = None,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
        retriever: Retriever | None = None,
        reranker: Reranker | None = None,
        context_builder: ContextBuilder | None = None,
        tracer: Any | None = None,
    ) -> None:
        self.config = config or RagConfig()
        self.loader = loader or LocalDirectoryLoader()
        self.parser = parser or TextParser()
        self.chunker = chunker or RecursiveChunker(
            chunk_size=self.config.chunker.chunk_size,
            chunk_overlap=self.config.chunker.chunk_overlap,
        )
        self.embedder = embedder or MockEmbedder()
        self.vector_store = vector_store or MemoryVectorStore()
        self.retriever = retriever or DenseRetriever(self.embedder, self.vector_store)
        self.reranker = reranker or NoopReranker()
        self.context_builder = context_builder or SimpleContextBuilder()
        self.tracer = tracer or NullTracer()

    async def index(self, source: dict[str, Any], tenant_id: str | None = None) -> list[Chunk]:
        effective_tenant_id = tenant_id or self.config.tenant_id
        trace_id = await self.tracer.start_trace(
            "rag.index",
            {"tenant_id": effective_tenant_id, "source": source},
        )
        documents = await self.loader.load({**source, "tenant_id": effective_tenant_id})
        parsed_documents = [await self.parser.parse(document) for document in documents]
        chunks = [
            chunk
            for document in parsed_documents
            for chunk in await self.chunker.chunk(document)
        ]
        embeddings = await self.embedder.embed_texts([chunk.text for chunk in chunks])
        embedded_chunks = [
            EmbeddedChunk(
                id=chunk.id,
                document_id=chunk.document_id,
                text=chunk.text,
                metadata={**chunk.metadata, "tenant_id": effective_tenant_id},
                embedding=embedding,
                embedding_model=self.embedder.model_name,
                embedding_dimension=self.embedder.dimension,
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        await self.vector_store.upsert(embedded_chunks)
        await self.tracer.add_event(
            trace_id,
            "indexed",
            {"document_count": len(documents), "chunk_count": len(chunks)},
        )
        await self.tracer.end_trace(trace_id, {"chunk_count": len(chunks)})
        return chunks

    async def retrieve(
        self,
        query: str,
        tenant_id: str | None = None,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[Any]:
        effective_tenant_id = tenant_id or self.config.tenant_id
        request = RetrievalRequest(
            query=query,
            tenant_id=effective_tenant_id,
            top_k=top_k or self.config.retriever.top_k,
            filters=filters or {},
            score_threshold=self.config.retriever.score_threshold,
        )
        chunks = await self.retriever.retrieve(request)
        reranked = await self.reranker.rerank(query, chunks)
        return reranked[: self.config.reranker.top_n]

    async def answer(
        self,
        query: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> RagAnswer:
        effective_tenant_id = tenant_id or self.config.tenant_id
        trace_id = await self.tracer.start_trace(
            "rag.answer",
            {"tenant_id": effective_tenant_id, "user_id": user_id, "query": query},
        )
        chunks = await self.retrieve(
            query=query,
            tenant_id=effective_tenant_id,
            top_k=top_k,
            filters=filters,
        )
        context = await self.context_builder.build(
            query,
            chunks,
            max_tokens=self.config.context.max_tokens,
        )
        answer = self._extractive_answer(query, context.text)
        await self.tracer.add_event(
            trace_id,
            "context_built",
            {
                "selected_chunk_count": len(context.chunks),
                "context_token_count": context.token_count,
            },
        )
        await self.tracer.end_trace(trace_id, {"citation_count": len(context.citations)})
        return RagAnswer(answer=answer, context=replace(context), trace_id=trace_id)

    @staticmethod
    def _extractive_answer(query: str, context: str) -> str:
        if not context:
            return "找不到足夠的相關內容。"
        return context

