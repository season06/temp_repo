# RAG Adapter — RAGAS Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: subagent-driven-development / executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** 以 **RAGAS** 補上答案/上下文品質評估(faithfulness、answer relevancy、context precision/recall),judge LLM 與 embeddings 重用 Qwen(OpenAI 相容)。沿用既有的確定性 retrieval 指標(`rag_adapter/evaluation/metrics.py`)。

**Architecture:** 我們的膠水(`QueryPipeline.retrieve`、樣本收集、config、factory)完全確定且有單元測試;所有 **RAGAS 專屬呼叫集中在 `rag_adapter/evaluation/ragas_eval.py` 一個模組**,RAGAS 與 langchain-openai 為選配依賴(lazy import)。RAGAS 透過 OpenAI 相容端點重用 Qwen 作為 judge LLM 與 embedding model。

**Tech Stack:** Python 3.10+、asyncio、pytest(+ pytest-asyncio);選配:`ragas`、`langchain-openai`、`datasets`。

> 規格依據:`docs/superpowers/specs/2026-06-14-rag-adapter-design.md`(Evaluation 路線 B:answer/context quality 以 judge LLM)。
> 決策:(1) judge 重用 Qwen,透過 `langchain-openai` 指向 Qwen 端點再包成 RAGAS wrapper;(2) RAGAS 為選配重依賴;(3) RAGAS API 版本敏感——集中於單一模組並標明適配點;(4) 真正呼叫 LLM 的測試以 `importorskip` + 環境變數守門,預設跳過。
> 型別:最小註記;`config.py` 例外採 typed frozen dataclass。

> ⚠️ **版本適配點(僅此處)**:`ragas_eval.py` 的 metric 匯入與 `factory.build_ragas_judge` 的 wrapper 匯入路徑會因 RAGAS 版本而異。本計畫以廣為文件化的 `ragas.evaluate` + `ragas.metrics.*` + `LangchainLLMWrapper`/`LangchainEmbeddingsWrapper` 撰寫;實作時若安裝版本不同,僅需在這兩個函式內調整匯入,其餘邏輯不變。

---

## File Structure

```
pyproject.toml                          # 修改:新增 ragas 選配 extra
rag_adapter/
  pipeline/query.py                     # 修改:新增 public retrieve(query)
  config.py                             # 修改:EvaluationConfig
  factory.py                            # 修改:build_ragas_judge
  evaluation/
    ragas_eval.py                       # 新增:RagasCase / collect_samples / 指標解析 / evaluate_with_ragas
    __init__.py                         # 修改:匯出 RAGAS 相關(lazy)
tests/
  test_query_pipeline.py               # 修改:retrieve() 測試
  test_ragas_eval.py                   # 新增:確定性部分(collect_samples、指標解析以 importorskip)
  test_config.py                       # 修改:evaluation 區塊
  test_ragas_integration.py            # 新增:守門的 live 測試(預設 skip)
```

---

## Task 1: 選配依賴

**Files:** Modify `pyproject.toml`

- [ ] **Step 1:** 在 `[project.optional-dependencies]` 新增一組:
```toml
ragas = ["ragas>=0.2", "langchain-openai>=0.1", "datasets>=2.0"]
```
(其餘群組不動;`ragas` 不加入 `all`,因為它很重且為評估專用。)

- [ ] **Step 2: Commit**
```bash
git add pyproject.toml
git commit -m "chore: add optional ragas extra for answer-quality evaluation"
```

---

## Task 2: QueryPipeline.retrieve（取回重排後候選,供收集 contexts)

**Files:** Modify `rag_adapter/pipeline/query.py`、`tests/test_query_pipeline.py`

- [ ] **Step 1: 在 tests/test_query_pipeline.py 末端新增測試**
```python
async def test_query_pipeline_retrieve_returns_reranked_chunks():
    store, chunks = _build_store()
    await store.upsert(chunks)
    embedder = EchoEmbedder()
    pipeline = QueryPipeline(
        retrievers=[VectorRetriever(embedder, store)],
        fusion=PassthroughFusion(),
        reranker=NoopReranker(),
        context_builder=SimpleContextBuilder(),
        top_k=2,
    )

    results = await pipeline.retrieve("aaaa")

    ids = [rc.chunk.id for rc in results]
    assert "c2" in ids
    assert all(hasattr(rc, "score") for rc in results)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_query_pipeline.py::test_query_pipeline_retrieve_returns_reranked_chunks -q`
Expected: FAIL，`AttributeError: 'QueryPipeline' object has no attribute 'retrieve'`

- [ ] **Step 3: 在 query.py 新增 public retrieve**

於 `QueryPipeline` 中,在 `retrieve_context` 之前新增:
```python
    async def retrieve(self, query):
        _, reranked = await self._retrieve(query)
        return reranked
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_query_pipeline.py -q`
Expected: PASS（全部 passed）

- [ ] **Step 5: Commit**
```bash
git add rag_adapter/pipeline/query.py tests/test_query_pipeline.py
git commit -m "feat: expose reranked retrieval results via QueryPipeline.retrieve"
```

---

## Task 3: config EvaluationConfig

**Files:** Modify `rag_adapter/config.py`、`tests/test_config.py`

- [ ] **Step 1: config.py 新增 EvaluationConfig**

在 `RagConfig` 之前新增:
```python
@dataclass(frozen=True)
class EvaluationConfig:
    enabled: bool = False
    metrics: list = field(default_factory=lambda: [
        "faithfulness", "answer_relevancy", "context_precision", "context_recall",
    ])
    judge_base_url: str = ""
    judge_api_key: str = ""
    judge_model: str = "qwen-max"
    embedding_model: str = "qwen-embedding"
```
把 `RagConfig` 改為:
```python
@dataclass(frozen=True)
class RagConfig:
    indexing: IndexingConfig = field(default_factory=IndexingConfig)
    query: QueryConfig = field(default_factory=QueryConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
```
新增轉換函式並更新 `from_dict`:
```python
def _evaluation_from_dict(raw: dict) -> EvaluationConfig:
    return EvaluationConfig(**raw)


def from_dict(raw: dict) -> RagConfig:
    """把已插值的 dict 轉成 typed RagConfig。"""
    return RagConfig(
        indexing=_indexing_from_dict(raw.get("indexing", {})),
        query=_query_from_dict(raw.get("query", {})),
        evaluation=_evaluation_from_dict(raw.get("evaluation", {})),
    )
```

- [ ] **Step 2: tests/test_config.py 新增測試**

在 `_YAML` 結尾 `"""` 之前(query 區塊之後,與 indexing/query 同層)加入:
```python
evaluation:
  enabled: true
  metrics: [faithfulness, context_recall]
  judge_base_url: https://api/v1
  judge_api_key: ${ENV:QWEN_KEY}
  judge_model: qwen-max
  embedding_model: qwen-embedding
```
並在 `test_load_config_returns_typed_config_with_env_interpolation` 末端追加:
```python
    assert config.evaluation.enabled is True
    assert config.evaluation.metrics == ["faithfulness", "context_recall"]
    assert config.evaluation.judge_api_key == "secret-123"
    assert config.evaluation.judge_model == "qwen-max"
```

- [ ] **Step 3: 跑測試**

Run: `pytest tests/test_config.py -q`
Expected: PASS（全部 passed）

- [ ] **Step 4: Commit**
```bash
git add rag_adapter/config.py tests/test_config.py
git commit -m "feat: add evaluation (ragas judge) config schema"
```

---

## Task 4: ragas_eval 模組(收集樣本 + RAGAS 評估)

**Files:** Create `rag_adapter/evaluation/ragas_eval.py`; Modify `rag_adapter/evaluation/__init__.py`、`rag_adapter/factory.py`; Test `tests/test_ragas_eval.py`

- [ ] **Step 1: 寫失敗測試(只測確定性部分)**

`tests/test_ragas_eval.py`:
```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_ragas_eval.py::test_collect_samples_builds_ragas_rows -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'rag_adapter.evaluation.ragas_eval'`

- [ ] **Step 3: 實作 ragas_eval.py**

`rag_adapter/evaluation/ragas_eval.py`:
```python
from dataclasses import dataclass


@dataclass
class RagasCase:
    """RAGAS 評估的一筆輸入:問題與選配的標準答案(context_recall / correctness 需要)。"""
    question: str
    ground_truth: str = ""


async def collect_samples(pipeline, cases):
    """跑 query pipeline,為每個 case 收集 RAGAS 需要的欄位。

    pipeline 需提供 async retrieve(query) -> list[RetrievedChunk] 與 async answer(query) -> Answer。
    """
    samples = []
    for case in cases:
        reranked = await pipeline.retrieve(case.question)
        answer = await pipeline.answer(case.question)
        samples.append({
            "question": case.question,
            "answer": answer.text,
            "contexts": [rc.chunk.text for rc in reranked],
            "ground_truth": case.ground_truth,
        })
    return samples


def _resolve_metrics(names):
    # 版本適配點:依安裝的 ragas 版本調整匯入
    from ragas.metrics import (
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    )

    table = {
        "faithfulness": faithfulness,
        "answer_relevancy": answer_relevancy,
        "context_precision": context_precision,
        "context_recall": context_recall,
    }
    return [table[name] for name in names]


def evaluate_with_ragas(samples, metric_names, llm, embeddings):
    """以 RAGAS 對收集到的樣本評分。llm / embeddings 為 RAGAS 相容物件(見 factory.build_ragas_judge)。

    回傳 RAGAS 的結果物件(各指標分數)。
    """
    # 版本適配點:依安裝的 ragas 版本調整匯入
    from datasets import Dataset
    from ragas import evaluate

    dataset = Dataset.from_dict({
        "question": [s["question"] for s in samples],
        "answer": [s["answer"] for s in samples],
        "contexts": [s["contexts"] for s in samples],
        "ground_truth": [s["ground_truth"] for s in samples],
    })
    return evaluate(dataset, metrics=_resolve_metrics(metric_names), llm=llm, embeddings=embeddings)
```

- [ ] **Step 4: 在 factory.py 新增 build_ragas_judge**

於 `rag_adapter/factory.py` 檔尾新增(全部 lazy import,未裝 ragas/langchain-openai 時不影響其他 factory 功能):
```python
def build_ragas_judge(config):
    """以 config.evaluation 建立 RAGAS 相容的 judge LLM 與 embeddings(重用 Qwen,OpenAI 相容)。

    版本適配點:依安裝的 ragas / langchain-openai 版本調整匯入。
    """
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper

    evaluation = config.evaluation
    chat = ChatOpenAI(
        base_url=evaluation.judge_base_url,
        api_key=evaluation.judge_api_key,
        model=evaluation.judge_model,
        temperature=0,
    )
    embeddings = OpenAIEmbeddings(
        base_url=evaluation.judge_base_url,
        api_key=evaluation.judge_api_key,
        model=evaluation.embedding_model,
    )
    return LangchainLLMWrapper(chat), LangchainEmbeddingsWrapper(embeddings)
```

- [ ] **Step 5: 更新 evaluation/__init__.py**

在現有匯出後追加(RAGAS 相關以函式層 lazy import,故此處只匯出純物件):
```python
from rag_adapter.evaluation.ragas_eval import RagasCase, collect_samples, evaluate_with_ragas
```
並把 `RagasCase`、`collect_samples`、`evaluate_with_ragas` 加進 `__all__`。
(注意:`ragas_eval` 頂層**不得** import ragas/datasets——這些只在函式內 import,確保未裝 ragas 時 `import rag_adapter.evaluation` 仍可用。)

- [ ] **Step 6: 跑測試**

Run: `pytest tests/test_ragas_eval.py -q`
Expected: PASS（collect_samples 過;若未裝 ragas,兩個 _resolve_metrics 測試自動 skip）

- [ ] **Step 7: Commit**
```bash
git add rag_adapter/evaluation/ragas_eval.py rag_adapter/evaluation/__init__.py rag_adapter/factory.py tests/test_ragas_eval.py
git commit -m "feat: add ragas-based answer-quality evaluation module"
```

---

## Task 5: 守門的 live 整合測試 + 全套件驗證

**Files:** Create `tests/test_ragas_integration.py`

- [ ] **Step 1: 寫守門整合測試**

`tests/test_ragas_integration.py`(預設 skip;需 `ragas` 已裝 + `RAGAS_LIVE=1` + Qwen 環境變數):
```python
import os

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("RAGAS_LIVE") != "1",
    reason="set RAGAS_LIVE=1 (with ragas installed and QWEN_* env) to run live ragas eval",
)


async def test_ragas_end_to_end():
    pytest.importorskip("ragas")
    pytest.importorskip("langchain_openai")

    from rag_adapter.config import load_config
    from rag_adapter.factory import build_query_pipeline, build_ragas_judge
    from rag_adapter.evaluation.ragas_eval import RagasCase, collect_samples, evaluate_with_ragas

    config = load_config("examples/rag.yaml")  # 需 query.generation.enabled=true 與 QWEN_* 環境變數
    pipeline = build_query_pipeline(config)
    llm, embeddings = build_ragas_judge(config)

    samples = await collect_samples(pipeline, [RagasCase(question="如何請假?", ground_truth="提前三天於系統申請")])
    result = evaluate_with_ragas(samples, config.evaluation.metrics, llm, embeddings)

    assert result is not None
```

- [ ] **Step 2: 確認預設會 skip**

Run: `pytest tests/test_ragas_integration.py -q`
Expected: 1 skipped(未設 `RAGAS_LIVE=1`)

- [ ] **Step 3: 全套件**

Run: `pytest -q`
Expected: PASS(既有 64 + 本階段確定性新增;ragas 相關若未裝則 skip,無 fail)

- [ ] **Step 4: Commit**
```bash
git add tests/test_ragas_integration.py
git commit -m "test: add guarded live ragas evaluation integration"
```

---

## Self-Review

**Spec coverage(Evaluation 路線 B,answer/context quality):** RAGAS faithfulness / answer_relevancy / context_precision / context_recall ✓;judge 重用 Qwen(OpenAI 相容)✓;沿用既有 retrieval 指標 ✓。
**依賴隔離:** ragas/langchain-openai/datasets 全為 lazy import(函式內);`import rag_adapter.evaluation` 不需裝 ragas ✓。
**測試分層:** 確定性(collect_samples)單元測;指標解析以 `importorskip`;live 評估以 `RAGAS_LIVE` 守門,預設 skip,不進 CI ✓。
**版本適配:** 所有 RAGAS 專屬匯入集中在 `ragas_eval._resolve_metrics` / `evaluate_with_ragas` / `factory.build_ragas_judge` 三處,並標明 ✓。
**Placeholder scan:** 我方邏輯無 TBD;外部 API 適配點已明確標註(非 placeholder,屬外部依賴調適)。

---

## 使用方式(實作後)

```python
from rag_adapter.config import load_config
from rag_adapter.factory import build_query_pipeline, build_ragas_judge
from rag_adapter.evaluation import RagasCase, collect_samples, evaluate_with_ragas

config = load_config("examples/rag.yaml")          # query.generation.enabled=true
pipeline = build_query_pipeline(config)
llm, embeddings = build_ragas_judge(config)         # 重用 Qwen
samples = await collect_samples(pipeline, [RagasCase("如何請假?", ground_truth="...")])
print(evaluate_with_ragas(samples, config.evaluation.metrics, llm, embeddings))
```

## 後續
- Observability(Langfuse trace)。
- 把 retrieval 指標與 RAGAS 報告合併成單一評估報表。
```

