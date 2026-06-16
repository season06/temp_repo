from rag_adapter.models import Chunk
from rag_adapter.pipeline.query import QueryPipeline
from rag_adapter.retrievers.dense_retriever import DenseRetriever
from rag_adapter.fusion.rrf_fusion import RRFFusion
from rag_adapter.context.context_builder import DefaultContextBuilder
from rag_adapter.prompts.template_prompt_builder import TemplatePromptBuilder
from rag_adapter.testing.mocks import EchoEmbedder, InMemoryVectorStore, NoopReranker, EchoGenerator


async def _pipeline():
    store = InMemoryVectorStore()
    await store.upsert([
        Chunk(id="c1", document_id="d", text="aa", embedding=[2.0]),
        Chunk(id="c2", document_id="d", text="aaaa", embedding=[4.0]),
    ])
    return QueryPipeline(
        retrievers=[DenseRetriever(EchoEmbedder(), store)],
        fusion=RRFFusion(),
        reranker=NoopReranker(),
        context_builder=DefaultContextBuilder(max_chars=1000),
        prompt_builder=TemplatePromptBuilder(),
        generator=EchoGenerator(),
        top_k=2,
    )


async def test_answer_runs_full_pipeline_with_real_prompt_builder():
    pipeline = await _pipeline()

    answer = await pipeline.answer("aaaa")

    assert answer.text.startswith("ANSWER:")
    assert "aaaa" in answer.text
    assert {c.chunk_id for c in answer.citations} == {"c1", "c2"}


async def test_stream_runs_full_pipeline():
    pipeline = await _pipeline()

    tokens = [token async for token in pipeline.stream("aaaa")]

    assert len(tokens) > 0
