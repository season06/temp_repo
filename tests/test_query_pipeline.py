from rag_adapter.models import Document, Chunk
from rag_adapter.testing.mocks import (
    InMemoryVectorStore,
    EchoEmbedder,
    PassthroughChunker,
    PassthroughParser,
    VectorRetriever,
    PassthroughFusion,
    NoopReranker,
    SimpleContextBuilder,
    TemplatePromptBuilder,
    EchoGenerator,
)
from rag_adapter.pipeline.query import QueryPipeline


async def test_echo_embedder_fills_embedding():
    chunk = Chunk(id="c1", document_id="d1", text="ab")
    out = await EchoEmbedder().embed([chunk])
    assert out[0].embedding == [2.0]


async def test_vector_store_upsert_and_search():
    store = InMemoryVectorStore()
    c1 = Chunk(id="c1", document_id="d1", text="aa", embedding=[2.0])
    c2 = Chunk(id="c2", document_id="d1", text="aaaa", embedding=[4.0])
    await store.upsert([c1, c2])
    results = await store.search([4.0], top_k=1)
    assert results[0].chunk.id == "c2"


def test_passthrough_chunker_one_chunk_per_doc():
    doc = Document(id="d1", text="hello world")
    chunks = PassthroughChunker().chunk(doc)
    assert len(chunks) == 1
    assert chunks[0].document_id == "d1"
    assert chunks[0].text == "hello world"


def _build_store():
    store = InMemoryVectorStore()
    c1 = Chunk(id="c1", document_id="d1", text="aa", embedding=[2.0])
    c2 = Chunk(id="c2", document_id="d1", text="aaaa", embedding=[4.0])
    return store, [c1, c2]


def _build_pipeline(store):
    embedder = EchoEmbedder()
    return QueryPipeline(
        retrievers=[VectorRetriever(embedder, store)],
        fusion=PassthroughFusion(),
        reranker=NoopReranker(),
        context_builder=SimpleContextBuilder(),
        prompt_builder=TemplatePromptBuilder(),
        generator=EchoGenerator(),
        top_k=2,
    )


async def test_query_pipeline_returns_answer_with_citations():
    store, chunks = _build_store()
    await store.upsert(chunks)
    pipeline = _build_pipeline(store)

    answer = await pipeline.answer("aaaa")

    assert answer.text.startswith("ANSWER:")
    assert "aaaa" in answer.text
    citation_ids = [c.chunk_id for c in answer.citations]
    assert "c2" in citation_ids


async def test_query_pipeline_stream_yields_tokens():
    store, chunks = _build_store()
    await store.upsert(chunks)
    pipeline = _build_pipeline(store)

    tokens = [token async for token in pipeline.stream("aaaa")]

    assert len(tokens) > 0
    assert "Question:" in " ".join(tokens)


def test_public_exports():
    import rag_adapter

    assert hasattr(rag_adapter, "IndexingPipeline")
    assert hasattr(rag_adapter, "QueryPipeline")
    assert hasattr(rag_adapter, "Document")
    assert hasattr(rag_adapter, "Chunk")
    assert hasattr(rag_adapter, "Answer")
