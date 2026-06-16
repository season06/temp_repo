from rag_adapter.models import Chunk
from rag_adapter.retrievers.dense_retriever import DenseRetriever
from rag_adapter.testing.mocks import EchoEmbedder, InMemoryVectorStore
from rag_adapter.evaluation import EvalCase, evaluate_retriever


async def test_evaluate_dense_retriever():
    store = InMemoryVectorStore()
    await store.upsert([
        Chunk(id="c1", document_id="d", text="aa", embedding=[2.0]),
        Chunk(id="c2", document_id="d", text="aaaa", embedding=[4.0]),
    ])
    retriever = DenseRetriever(EchoEmbedder(), store)
    cases = [EvalCase(query="aaaa", relevant_ids=["c2"])]

    report = await evaluate_retriever(retriever, cases, k=2)

    assert report.num_cases == 1
    assert report.recall == 1.0
    assert report.mrr == 1.0
