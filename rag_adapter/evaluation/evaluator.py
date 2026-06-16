from dataclasses import dataclass, field

from rag_adapter.evaluation.metrics import (
    recall_at_k,
    precision_at_k,
    reciprocal_rank,
    ndcg_at_k,
)


@dataclass
class EvalReport:
    """聚合後的 retrieval 評估結果(各指標為全 case 平均)。"""
    k: int
    num_cases: int
    recall: float
    precision: float
    mrr: float
    ndcg: float
    per_case: list = field(default_factory=list)


def _mean(values):
    return sum(values) / len(values) if values else 0.0


class RetrievalEvaluator:
    """離線 retrieval 評估器。evaluate 吃 async retrieve 函式 (query, k) -> list[chunk_id]。"""

    def __init__(self, k=10):
        self._k = k

    async def evaluate(self, retrieve_fn, cases):
        per_case = []
        for case in cases:
            retrieved = await retrieve_fn(case.query, self._k)
            per_case.append({
                "query": case.query,
                "recall": recall_at_k(retrieved, case.relevant_ids, self._k),
                "precision": precision_at_k(retrieved, case.relevant_ids, self._k),
                "rr": reciprocal_rank(retrieved, case.relevant_ids),
                "ndcg": ndcg_at_k(retrieved, case.relevant_ids, self._k),
            })
        return EvalReport(
            k=self._k,
            num_cases=len(per_case),
            recall=_mean([c["recall"] for c in per_case]),
            precision=_mean([c["precision"] for c in per_case]),
            mrr=_mean([c["rr"] for c in per_case]),
            ndcg=_mean([c["ndcg"] for c in per_case]),
            per_case=per_case,
        )


async def evaluate_retriever(retriever, cases, k=10):
    """便捷:直接評估一個 Retriever(取其回傳 chunk 的 id 排序)。"""
    async def retrieve_fn(query, top_k):
        results = await retriever.retrieve(query, top_k)
        return [rc.chunk.id for rc in results]

    return await RetrievalEvaluator(k=k).evaluate(retrieve_fn, cases)
