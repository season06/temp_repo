from rag_adapter.evaluation.dataset import EvalCase
from rag_adapter.evaluation.evaluator import RetrievalEvaluator, EvalReport, evaluate_retriever
from rag_adapter.models import Chunk, RetrievedChunk


async def test_evaluator_aggregates_metrics():
    cases = [
        EvalCase(query="q1", relevant_ids=["c1"]),
        EvalCase(query="q2", relevant_ids=["c2"]),
    ]
    routing = {
        "q1": ["c1", "c9"],
        "q2": ["c9", "c2"],
    }

    async def retrieve_fn(query, k):
        return routing[query][:k]

    report = await RetrievalEvaluator(k=2).evaluate(retrieve_fn, cases)

    assert isinstance(report, EvalReport)
    assert report.num_cases == 2
    assert report.k == 2
    assert report.recall == 1.0
    assert report.mrr == (1.0 + 0.5) / 2
    assert len(report.per_case) == 2


async def test_evaluate_retriever_helper():
    class StubRetriever:
        async def retrieve(self, query, top_k):
            return [
                RetrievedChunk(chunk=Chunk(id="c1", document_id="d", text="t"), score=1.0),
                RetrievedChunk(chunk=Chunk(id="c2", document_id="d", text="t"), score=0.5),
            ][:top_k]

    cases = [EvalCase(query="q", relevant_ids=["c2"])]

    report = await evaluate_retriever(StubRetriever(), cases, k=2)

    assert report.num_cases == 1
    assert report.recall == 1.0
    assert report.mrr == 0.5
