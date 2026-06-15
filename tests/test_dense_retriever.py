from rag_adapter.models import Chunk
from rag_adapter.retrievers.dense_retriever import DenseRetriever
from rag_adapter.testing.mocks import EchoEmbedder, InMemoryVectorStore


async def test_dense_retriever_embeds_query_and_searches():
    store = InMemoryVectorStore()
    await store.upsert([
        Chunk(id="c1", document_id="d", text="aa", embedding=[2.0]),
        Chunk(id="c2", document_id="d", text="aaaa", embedding=[4.0]),
    ])
    retriever = DenseRetriever(EchoEmbedder(), store)

    results = await retriever.retrieve("aaaa", top_k=1)

    assert results[0].chunk.id == "c2"
