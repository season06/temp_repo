import math

from rag_adapter.evaluation.metrics import (
    recall_at_k,
    precision_at_k,
    reciprocal_rank,
    ndcg_at_k,
)


def test_recall_at_k():
    assert recall_at_k(["c1", "c2", "c3"], ["c1", "c3"], 3) == 1.0
    assert recall_at_k(["c2", "c4"], ["c1", "c3"], 3) == 0.0
    assert recall_at_k([], ["c1"], 3) == 0.0
    assert recall_at_k(["c1"], [], 3) == 0.0


def test_precision_at_k():
    assert precision_at_k(["c1", "c2", "c3"], ["c1", "c3"], 3) == 2 / 3
    assert precision_at_k([], ["c1"], 3) == 0.0


def test_reciprocal_rank():
    assert reciprocal_rank(["c1", "c2"], ["c1"]) == 1.0
    assert reciprocal_rank(["c2", "c1"], ["c1"]) == 0.5
    assert reciprocal_rank(["c2", "c3"], ["c1"]) == 0.0


def test_ndcg_at_k():
    value = ndcg_at_k(["c1", "c2", "c3"], ["c1", "c3"], 3)
    expected = (1.0 + 1.0 / math.log2(4)) / (1.0 + 1.0 / math.log2(3))
    assert abs(value - expected) < 1e-9
    assert ndcg_at_k(["c2"], ["c1"], 3) == 0.0
