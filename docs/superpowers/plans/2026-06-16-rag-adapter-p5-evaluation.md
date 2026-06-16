# RAG Adapter — P5 Evaluation (Retrieval Metrics) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: subagent-driven-development / executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** 提供離線 **Retrieval 評估**:純計算的指標(recall@k / precision@k / MRR / nDCG@k)、評估資料集模型 `EvalCase`,以及 `RetrievalEvaluator`(吃一個 async retrieve 函式或 Retriever,輸出 `EvalReport`)。

**Architecture:** 評估為離線、橫切工具,不屬 query pipeline 的一步。指標為純函式(sync);`RetrievalEvaluator.evaluate` 為 async(逐 case 呼叫 async retrieve)。零外部依賴。

**Tech Stack:** Python 3.10+、stdlib(math)、pytest + pytest-asyncio。

> 規格依據:`docs/superpowers/specs/2026-06-14-rag-adapter-design.md`(Evaluation 路線 B;v1 先做 Retrieval 指標)
> 範圍取捨:Context 品質與 Answer quality(faithfulness / answer relevance,需 judge LLM)**本階段延後**;先交付 Retrieval 指標 + 介面。Observability(Langfuse)亦不在本階段。
> 型別:最小註記;dataclass 欄位照常。

---

## File Structure

```
rag_adapter/evaluation/
  __init__.py            # 對外匯出
  metrics.py             # recall_at_k / precision_at_k / reciprocal_rank / ndcg_at_k
  dataset.py             # EvalCase
  evaluator.py           # RetrievalEvaluator / EvalReport / evaluate_retriever
tests/
  test_eval_metrics.py
  test_evaluator.py
```

---

## Task 1: 指標(metrics)

**Files:**
- Create: `rag_adapter/evaluation/__init__.py`(暫空字串)、`rag_adapter/evaluation/metrics.py`
- Test: `tests/test_eval_metrics.py`

- [ ] **Step 1: 寫失敗測試**

`tests/test_eval_metrics.py`:
```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_eval_metrics.py -q`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 實作 metrics.py**

`rag_adapter/evaluation/metrics.py`:
```python
import math


def recall_at_k(retrieved_ids, relevant_ids, k):
    """top-k 命中的相關項數 / 全部相關項數。"""
    relevant = set(relevant_ids)
    if not relevant:
        return 0.0
    hits = len(set(retrieved_ids[:k]) & relevant)
    return hits / len(relevant)


def precision_at_k(retrieved_ids, relevant_ids, k):
    """top-k 中相關項的比例(分母為實際取到的數量,最多 k)。"""
    top = retrieved_ids[:k]
    if not top:
        return 0.0
    hits = len(set(top) & set(relevant_ids))
    return hits / len(top)


def reciprocal_rank(retrieved_ids, relevant_ids):
    """第一個相關項的 1/排名(找不到為 0)。"""
    relevant = set(relevant_ids)
    for index, rid in enumerate(retrieved_ids):
        if rid in relevant:
            return 1.0 / (index + 1)
    return 0.0


def ndcg_at_k(retrieved_ids, relevant_ids, k):
    """二元相關度的 nDCG@k。"""
    relevant = set(relevant_ids)
    dcg = 0.0
    for index, rid in enumerate(retrieved_ids[:k]):
        if rid in relevant:
            dcg += 1.0 / math.log2(index + 2)
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    return dcg / idcg if idcg > 0 else 0.0
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_eval_metrics.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/evaluation/__init__.py rag_adapter/evaluation/metrics.py tests/test_eval_metrics.py
git commit -m "feat: add retrieval evaluation metrics"
```

---

## Task 2: 資料集與評估器

**Files:**
- Create: `rag_adapter/evaluation/dataset.py`、`rag_adapter/evaluation/evaluator.py`
- Modify: `rag_adapter/evaluation/__init__.py`
- Test: `tests/test_evaluator.py`

- [ ] **Step 1: 寫失敗測試**

`tests/test_evaluator.py`:
```python
from rag_adapter.evaluation.dataset import EvalCase
from rag_adapter.evaluation.evaluator import RetrievalEvaluator, EvalReport, evaluate_retriever
from rag_adapter.models import Chunk, RetrievedChunk


async def test_evaluator_aggregates_metrics():
    cases = [
        EvalCase(query="q1", relevant_ids=["c1"]),
        EvalCase(query="q2", relevant_ids=["c2"]),
    ]
    # q1 → c1 第一名(完美);q2 → c2 第二名
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_evaluator.py -q`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 實作 dataset.py**

`rag_adapter/evaluation/dataset.py`:
```python
from dataclasses import dataclass, field


@dataclass
class EvalCase:
    """一筆評估案例:query 與其相關(golden)chunk ids。"""
    query: str
    relevant_ids: list = field(default_factory=list)
```

- [ ] **Step 4: 實作 evaluator.py**

`rag_adapter/evaluation/evaluator.py`:
```python
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
```

- [ ] **Step 5: 更新 __init__.py**

`rag_adapter/evaluation/__init__.py`:
```python
from rag_adapter.evaluation.dataset import EvalCase
from rag_adapter.evaluation.evaluator import RetrievalEvaluator, EvalReport, evaluate_retriever
from rag_adapter.evaluation.metrics import (
    recall_at_k,
    precision_at_k,
    reciprocal_rank,
    ndcg_at_k,
)

__all__ = [
    "EvalCase",
    "RetrievalEvaluator",
    "EvalReport",
    "evaluate_retriever",
    "recall_at_k",
    "precision_at_k",
    "reciprocal_rank",
    "ndcg_at_k",
]
```

- [ ] **Step 6: 跑測試確認通過**

Run: `pytest tests/test_evaluator.py -q`
Expected: PASS（2 passed）

- [ ] **Step 7: Commit**

```bash
git add rag_adapter/evaluation/dataset.py rag_adapter/evaluation/evaluator.py rag_adapter/evaluation/__init__.py tests/test_evaluator.py
git commit -m "feat: add retrieval evaluator and eval dataset model"
```

---

## Task 3: 整合測試 + 全套件驗證

**Files:**
- Test: `tests/test_evaluation_integration.py`

- [ ] **Step 1: 寫整合測試**(真實 DenseRetriever over in-memory store)

`tests/test_evaluation_integration.py`:
```python
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
    # EchoEmbedder: query 向量 = len(query);"aaaa"(4) 應最接近 c2(4.0)
    cases = [EvalCase(query="aaaa", relevant_ids=["c2"])]

    report = await evaluate_retriever(retriever, cases, k=2)

    assert report.num_cases == 1
    assert report.recall == 1.0
    assert report.mrr == 1.0
```

- [ ] **Step 2: 跑整合測試**

Run: `pytest tests/test_evaluation_integration.py -q`
Expected: PASS（1 passed）

- [ ] **Step 3: 全套件**

Run: `pytest -q`
Expected: PASS(P1–P4 既有 57 + Evaluation 新增,全部 passed)

- [ ] **Step 4: Commit**

```bash
git add tests/test_evaluation_integration.py
git commit -m "test: add retrieval evaluation integration"
```

---

## Self-Review

**Spec coverage(Evaluation 路線 B,v1):** Retrieval 指標(recall/precision/MRR/nDCG)✓;EvalCase 資料集 ✓;Evaluator + 便捷 helper ✓。Context 品質 / Answer quality(judge LLM)— 延後(已標明)。
**Async 邊界:** 指標為純函式 sync;evaluate 為 async(逐 case await retrieve)✓
**Placeholder scan:** 無 TBD/TODO;每步皆有完整程式碼。
**一致性:** retrieve_fn 簽章 (query, k) -> list[chunk_id];evaluate_retriever 由 Retriever 的 RetrievedChunk 取 chunk.id;EvalReport 各指標為平均。

---

## 後續(另開 docs)
- **Answer / Context quality 評估**:接 judge LLM(faithfulness、answer relevance、context relevance)。
- **Observability**:Langfuse trace(本次略過)。
