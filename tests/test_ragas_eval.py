import pytest

from rag_adapter.models import Chunk, RetrievedChunk, Answer
from rag_adapter.evaluation.ragas_eval import RagasCase, collect_samples


class FakePipeline:
    """模擬 QueryPipeline:retrieve 回傳重排候選,answer 回傳 Answer。"""
    async def retrieve(self, query):
        return [
            RetrievedChunk(chunk=Chunk(id="c1", document_id="d", text="alpha"), score=1.0),
            RetrievedChunk(chunk=Chunk(id="c2", document_id="d", text="beta"), score=0.5),
        ]

    async def answer(self, query):
        return Answer(text=f"answer for {query}", citations=[])


async def test_collect_samples_builds_ragas_rows():
    pipeline = FakePipeline()
    cases = [RagasCase(question="q1", ground_truth="gt1")]

    samples = await collect_samples(pipeline, cases)

    assert samples == [{
        "question": "q1",
        "answer": "answer for q1",
        "contexts": ["alpha", "beta"],
        "ground_truth": "gt1",
    }]


def test_resolve_metrics_maps_names():
    pytest.importorskip("ragas")
    from rag_adapter.evaluation.ragas_eval import _resolve_metrics

    metrics = _resolve_metrics(["faithfulness", "answer_relevancy"])

    assert len(metrics) == 2


def test_resolve_metrics_rejects_unknown():
    pytest.importorskip("ragas")
    from rag_adapter.evaluation.ragas_eval import _resolve_metrics

    with pytest.raises(KeyError):
        _resolve_metrics(["nope"])
