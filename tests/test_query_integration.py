from rag_adapter.models import Chunk
from rag_adapter.pipeline.query import QueryPipeline
from rag_adapter.retrievers.dense_retriever import DenseRetriever
from rag_adapter.fusion.rrf_fusion import RRFFusion
from rag_adapter.context.context_builder import DefaultContextBuilder
from rag_adapter.testing.mocks import EchoEmbedder, InMemoryVectorStore, NoopReranker


async def test_query_pipeline_retrieve_context_end_to_end():
    store = InMemoryVectorStore()
    await store.upsert([
        Chunk(id="c1", document_id="d", text="aa", embedding=[2.0]),
        Chunk(id="c2", document_id="d", text="aaaa", embedding=[4.0]),
    ])
    pipeline = QueryPipeline(
        retrievers=[DenseRetriever(EchoEmbedder(), store)],
        fusion=RRFFusion(),
        reranker=NoopReranker(),
        context_builder=DefaultContextBuilder(max_chars=1000),
        top_k=2,
    )

    built = await pipeline.retrieve_context("aaaa")

    assert "[1]" in built["context"]
    assert {c.chunk_id for c in built["citations"]} == {"c1", "c2"}
