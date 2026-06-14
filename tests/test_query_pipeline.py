from rag_adapter.models import Document, Chunk
from rag_adapter.testing.mocks import (
    InMemoryVectorStore,
    EchoEmbedder,
    PassthroughChunker,
    PassthroughParser,
)


def test_echo_embedder_fills_embedding():
    chunk = Chunk(id="c1", document_id="d1", text="ab")
    out = EchoEmbedder().embed([chunk])
    assert out[0].embedding == [2.0]  # 以文字長度當作向量


def test_vector_store_upsert_and_search():
    store = InMemoryVectorStore()
    c1 = Chunk(id="c1", document_id="d1", text="aa", embedding=[2.0])
    c2 = Chunk(id="c2", document_id="d1", text="aaaa", embedding=[4.0])
    store.upsert([c1, c2])
    results = store.search([4.0], top_k=1)
    assert results[0].chunk.id == "c2"


def test_passthrough_chunker_one_chunk_per_doc():
    doc = Document(id="d1", text="hello world")
    chunks = PassthroughChunker().chunk(doc)
    assert len(chunks) == 1
    assert chunks[0].document_id == "d1"
    assert chunks[0].text == "hello world"
