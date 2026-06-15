# RAG Adapter — P3 Query Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 補上 Query 側真實 provider:DenseRetriever(cosine)、BM25Retriever(sparse)、RRFFusion、QwenReranker(API),以及 DefaultContextBuilder;讓 `QueryPipeline` 能端到端跑「檢索→融合→重排→組裝 context」並產出引用。生成(Generator)屬 P4。

**Architecture:** 沿用既有 Protocol 與 async 邊界。Async I/O 層:Retriever.retrieve、Reranker.rerank。Sync CPU 層:Fusion.fuse、ContextBuilder.build。`QueryPipeline` 新增 `retrieve_context()`,並把 `prompt_builder`/`generator` 改為可選(P4 才接生成)。config 擴充 `query` 區塊,factory 新增 `build_query_pipeline`。

**Tech Stack:** Python 3.10+、asyncio、httpx.AsyncClient(reranker)、rank-bm25(BM25)、pytest + pytest-asyncio。

> 規格依據:`docs/superpowers/specs/2026-06-14-rag-adapter-design.md`
> 設計取捨:(1) 新增 `retrieve_context`、生成可選(生成=P4);(2) BM25 的 config 驅動延後(需語料),P3 實作 BM25Retriever 供手動 hybrid;(3) reranker 回傳數量由 pipeline `top_k` 決定。
> 型別:維持最小註記;`config.py` 例外採 typed frozen dataclass。

---

## File Structure

```
pyproject.toml                          # 修改:新增 rank-bm25 相依
rag_adapter/
  pipeline/query.py                     # 修改:retrieve_context + 可選 generator
  retrievers/
    __init__.py
    dense_retriever.py                  # DenseRetriever(cosine via embedder+store)
    bm25_retriever.py                   # BM25Retriever(in-memory sparse)
  fusion/
    __init__.py
    rrf_fusion.py                       # RRFFusion
  rerankers/
    __init__.py
    qwen_reranker.py                    # QwenReranker(API)
  context/
    __init__.py
    context_builder.py                  # DefaultContextBuilder
  config.py                             # 修改:新增 query schema
  factory.py                            # 修改:build_query_pipeline
tests/
  test_query_pipeline.py               # 修改:加 retrieve_context 測試
  test_dense_retriever.py
  test_bm25_retriever.py
  test_rrf_fusion.py
  test_qwen_reranker.py
  test_context_builder.py
  test_config.py                       # 修改:query config 斷言
  test_factory.py                      # 修改:build_query_pipeline 斷言
  test_query_integration.py
```

---

## Task 1: 相依與套件目錄

**Files:**
- Modify: `pyproject.toml`
- Create: `rag_adapter/retrievers/__init__.py`、`rag_adapter/fusion/__init__.py`、`rag_adapter/rerankers/__init__.py`、`rag_adapter/context/__init__.py`

- [ ] **Step 1: 更新 pyproject.toml**

把 `[project.optional-dependencies]` 整段替換為:
```toml
[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "beautifulsoup4>=4.12", "httpx>=0.27", "qdrant-client>=1.9", "rank-bm25>=0.2"]
html = ["beautifulsoup4>=4.12"]
http = ["httpx>=0.27"]
qdrant = ["qdrant-client>=1.9"]
bm25 = ["rank-bm25>=0.2"]
all = ["beautifulsoup4>=4.12", "httpx>=0.27", "qdrant-client>=1.9", "rank-bm25>=0.2"]
```

- [ ] **Step 2: 建立空 package 檔**

以下四檔內容皆為空字串:
`rag_adapter/retrievers/__init__.py`、`rag_adapter/fusion/__init__.py`、`rag_adapter/rerankers/__init__.py`、`rag_adapter/context/__init__.py`

- [ ] **Step 3: 安裝並驗證**

Run: `pip install -e ".[dev]" && python -c "import rank_bm25; print('bm25 ok')"`
Expected: 印出 `bm25 ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml rag_adapter/retrievers/__init__.py rag_adapter/fusion/__init__.py rag_adapter/rerankers/__init__.py rag_adapter/context/__init__.py
git commit -m "chore: add rank-bm25 dep and query package dirs"
```

---

## Task 2: QueryPipeline 加 retrieve_context、生成改可選

**Files:**
- Modify: `rag_adapter/pipeline/query.py`
- Modify: `tests/test_query_pipeline.py`

- [ ] **Step 1: 改 pipeline/query.py**

`rag_adapter/pipeline/query.py` 全檔改為:
```python
class QueryPipeline:
    """依序執行 (transform?) → retrieve(多路) → fuse → rerank → build context
    →(可選)build prompt → generate。I/O 步驟以 await 執行。

    retrieve_context() 只跑到組裝 context(產出 context + 引用),不需 generator。
    answer()/stream() 需要 prompt_builder 與 generator(P4 才接);未提供時呼叫會報錯。
    """

    def __init__(
        self,
        retrievers,
        fusion,
        reranker,
        context_builder,
        top_k,
        prompt_builder=None,
        generator=None,
        query_transform=None,
    ):
        self._retrievers = retrievers
        self._fusion = fusion
        self._reranker = reranker
        self._context_builder = context_builder
        self._top_k = top_k
        self._prompt_builder = prompt_builder
        self._generator = generator
        self._query_transform = query_transform

    async def _retrieve(self, query):
        if self._query_transform is not None:
            query = self._query_transform.transform(query)
        ranked_lists = []
        for retriever in self._retrievers:
            ranked_lists.append(await retriever.retrieve(query, self._top_k))
        fused = self._fusion.fuse(ranked_lists, self._top_k)
        reranked = await self._reranker.rerank(query, fused, self._top_k)
        return query, reranked

    async def retrieve_context(self, query):
        prepared_query, reranked = await self._retrieve(query)
        return self._context_builder.build(prepared_query, reranked)

    async def _prepare(self, query):
        built = await self.retrieve_context(query)
        if self._prompt_builder is None or self._generator is None:
            raise RuntimeError("prompt_builder and generator are required for answer()/stream()")
        prompt = self._prompt_builder.build_prompt(query, built["context"])
        return prompt, built["citations"]

    async def answer(self, query):
        prompt, citations = await self._prepare(query)
        return await self._generator.generate(prompt, citations)

    async def stream(self, query):
        prompt, citations = await self._prepare(query)
        async for token in self._generator.stream(prompt, citations):
            yield token
```

- [ ] **Step 2: 在 tests/test_query_pipeline.py 末端新增 retrieve_context 測試**

於檔案末端追加:
```python
async def test_query_pipeline_retrieve_context_without_generator():
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

    built = await pipeline.retrieve_context("aaaa")

    assert "aaaa" in built["context"]
    assert [c.chunk_id for c in built["citations"]]


async def test_answer_without_generator_raises():
    import pytest

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

    with pytest.raises(RuntimeError):
        await pipeline.answer("aaaa")
```

- [ ] **Step 3: 跑測試**

Run: `pytest tests/test_query_pipeline.py -q`
Expected: PASS（既有 + 2 新增,全部 passed）

- [ ] **Step 4: Commit**

```bash
git add rag_adapter/pipeline/query.py tests/test_query_pipeline.py
git commit -m "feat: add retrieve_context and make generation optional in query pipeline"
```

---

## Task 3: DenseRetriever

**Files:**
- Create: `rag_adapter/retrievers/dense_retriever.py`
- Test: `tests/test_dense_retriever.py`

- [ ] **Step 1: 寫失敗測試**

`tests/test_dense_retriever.py`:
```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_dense_retriever.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'rag_adapter.retrievers.dense_retriever'`

- [ ] **Step 3: 實作 dense_retriever.py**

`rag_adapter/retrievers/dense_retriever.py`:
```python
class DenseRetriever:
    """以 embedder 將 query 轉向量,再用 vector store 做相似度檢索(cosine 由 store 設定)。"""

    def __init__(self, embedder, vector_store):
        self._embedder = embedder
        self._vector_store = vector_store

    async def retrieve(self, query, top_k):
        embedding = await self._embedder.embed_query(query)
        return await self._vector_store.search(embedding, top_k)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_dense_retriever.py -q`
Expected: PASS（1 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/retrievers/dense_retriever.py tests/test_dense_retriever.py
git commit -m "feat: add dense retriever"
```

---

## Task 4: BM25Retriever

**Files:**
- Create: `rag_adapter/retrievers/bm25_retriever.py`
- Test: `tests/test_bm25_retriever.py`

- [ ] **Step 1: 寫失敗測試**

`tests/test_bm25_retriever.py`:
```python
from rag_adapter.models import Chunk
from rag_adapter.retrievers.bm25_retriever import BM25Retriever


async def test_bm25_retriever_ranks_by_term_overlap():
    chunks = [
        Chunk(id="c1", document_id="d", text="the cat sat on the mat"),
        Chunk(id="c2", document_id="d", text="dogs run in the park"),
        Chunk(id="c3", document_id="d", text="a cat and a dog"),
    ]
    retriever = BM25Retriever(chunks)

    results = await retriever.retrieve("cat", top_k=2)

    ids = [rc.chunk.id for rc in results]
    assert "c1" in ids or "c3" in ids
    assert results[0].score >= results[1].score


async def test_bm25_retriever_empty_corpus():
    retriever = BM25Retriever([])

    assert await retriever.retrieve("anything", top_k=5) == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_bm25_retriever.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'rag_adapter.retrievers.bm25_retriever'`

- [ ] **Step 3: 實作 bm25_retriever.py**

`rag_adapter/retrievers/bm25_retriever.py`:
```python
from rank_bm25 import BM25Okapi

from rag_adapter.models import RetrievedChunk


def _tokenize(text):
    return text.lower().split()


class BM25Retriever:
    """以 BM25 對記憶體內 chunk 語料做稀疏檢索。語料於建構時提供。

    語料如何取得(索引期收集)屬整合層的責任;此類別只負責建索引與檢索。
    """

    def __init__(self, chunks):
        self._chunks = list(chunks)
        self._bm25 = BM25Okapi([_tokenize(c.text) for c in self._chunks]) if self._chunks else None

    async def retrieve(self, query, top_k):
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(zip(self._chunks, scores), key=lambda pair: pair[1], reverse=True)
        return [RetrievedChunk(chunk=chunk, score=float(score)) for chunk, score in ranked[:top_k]]
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_bm25_retriever.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/retrievers/bm25_retriever.py tests/test_bm25_retriever.py
git commit -m "feat: add in-memory bm25 retriever"
```

---

## Task 5: RRFFusion

**Files:**
- Create: `rag_adapter/fusion/rrf_fusion.py`
- Test: `tests/test_rrf_fusion.py`

- [ ] **Step 1: 寫失敗測試**

`tests/test_rrf_fusion.py`:
```python
from rag_adapter.models import Chunk, RetrievedChunk
from rag_adapter.fusion.rrf_fusion import RRFFusion


def _rc(cid):
    return RetrievedChunk(chunk=Chunk(id=cid, document_id="d", text=cid), score=0.0)


def test_rrf_fusion_merges_and_ranks():
    list1 = [_rc("c1"), _rc("c2"), _rc("c3")]
    list2 = [_rc("c2"), _rc("c3")]

    fused = RRFFusion(k=60).fuse([list1, list2], top_k=3)

    assert [rc.chunk.id for rc in fused] == ["c2", "c3", "c1"]
    assert fused[0].score > fused[1].score > fused[2].score


def test_rrf_fusion_dedupes_by_chunk_id():
    fused = RRFFusion().fuse([[_rc("c1")], [_rc("c1")]], top_k=5)

    assert len(fused) == 1
    assert fused[0].chunk.id == "c1"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_rrf_fusion.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'rag_adapter.fusion.rrf_fusion'`

- [ ] **Step 3: 實作 rrf_fusion.py**

`rag_adapter/fusion/rrf_fusion.py`:
```python
from rag_adapter.models import RetrievedChunk


class RRFFusion:
    """Reciprocal Rank Fusion:合併多路排序,score = Σ 1/(k + rank)(rank 自 1 起算)。"""

    def __init__(self, k=60):
        self._k = k

    def fuse(self, ranked_lists, top_k):
        scores = {}
        chunks = {}
        for ranked in ranked_lists:
            for rank, retrieved in enumerate(ranked):
                cid = retrieved.chunk.id
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (self._k + rank + 1)
                if cid not in chunks:
                    chunks[cid] = retrieved.chunk
        fused = [RetrievedChunk(chunk=chunks[cid], score=score) for cid, score in scores.items()]
        fused.sort(key=lambda rc: rc.score, reverse=True)
        return fused[:top_k]
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_rrf_fusion.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/fusion/rrf_fusion.py tests/test_rrf_fusion.py
git commit -m "feat: add rrf fusion"
```

---

## Task 6: QwenReranker（API)

**Files:**
- Create: `rag_adapter/rerankers/qwen_reranker.py`
- Test: `tests/test_qwen_reranker.py`

說明:呼叫 `POST {base_url}/rerank`,payload `{model, query, documents, top_n}`,回應 `{"results": [{"index", "relevance_score"}, ...]}`;依 index 對回候選,score 改為 relevance_score。回傳數量為 `top_k`。

- [ ] **Step 1: 寫失敗測試**

`tests/test_qwen_reranker.py`:
```python
from rag_adapter.models import Chunk, RetrievedChunk
from rag_adapter.rerankers.qwen_reranker import QwenReranker


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeHttpClient:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    async def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return FakeResponse(self._payload)


def _rc(cid, text):
    return RetrievedChunk(chunk=Chunk(id=cid, document_id="d", text=text), score=0.0)


async def test_reranker_reorders_by_relevance():
    candidates = [_rc("c1", "alpha"), _rc("c2", "beta"), _rc("c3", "gamma")]
    payload = {"results": [
        {"index": 2, "relevance_score": 0.9},
        {"index": 0, "relevance_score": 0.4},
    ]}
    client = FakeHttpClient(payload)
    reranker = QwenReranker(base_url="https://api/v1/", api_key="k", model="qwen-reranker", client=client)

    results = await reranker.rerank("q", candidates, top_k=2)

    assert [rc.chunk.id for rc in results] == ["c3", "c1"]
    assert results[0].score == 0.9
    assert client.calls[0]["url"] == "https://api/v1/rerank"
    assert client.calls[0]["headers"]["Authorization"] == "Bearer k"
    assert client.calls[0]["json"]["top_n"] == 2
    assert client.calls[0]["json"]["documents"] == ["alpha", "beta", "gamma"]


async def test_reranker_empty_candidates():
    client = FakeHttpClient({"results": []})
    reranker = QwenReranker(base_url="https://api/v1", api_key="k", model="m", client=client)

    assert await reranker.rerank("q", [], top_k=3) == []
    assert client.calls == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_qwen_reranker.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'rag_adapter.rerankers.qwen_reranker'`

- [ ] **Step 3: 實作 qwen_reranker.py**

`rag_adapter/rerankers/qwen_reranker.py`:
```python
import httpx

from rag_adapter.models import RetrievedChunk


class QwenReranker:
    """以 Qwen reranker API 對候選重排;回傳 top_k,score 改為 relevance score。"""

    def __init__(self, base_url, api_key, model, client=None):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=60)

    async def rerank(self, query, candidates, top_k):
        if not candidates:
            return []
        documents = [rc.chunk.text for rc in candidates]
        response = await self._client.post(
            f"{self._base_url}/rerank",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self._model, "query": query, "documents": documents, "top_n": top_k},
        )
        response.raise_for_status()
        reranked = []
        for item in response.json()["results"]:
            candidate = candidates[item["index"]]
            reranked.append(RetrievedChunk(chunk=candidate.chunk, score=item["relevance_score"]))
        return reranked
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_qwen_reranker.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/rerankers/qwen_reranker.py tests/test_qwen_reranker.py
git commit -m "feat: add qwen api reranker"
```

---

## Task 7: DefaultContextBuilder

**Files:**
- Create: `rag_adapter/context/context_builder.py`
- Test: `tests/test_context_builder.py`

說明:依字元預算組裝 context,去重(by chunk.id)、加 `[n]` 來源標記、產出引用;單一過長 chunk 仍至少納入一個。回傳 `{"context", "citations"}`。

- [ ] **Step 1: 寫失敗測試**

`tests/test_context_builder.py`:
```python
from rag_adapter.models import Chunk, RetrievedChunk, SourceRef
from rag_adapter.context.context_builder import DefaultContextBuilder


def _rc(cid, text):
    ref = SourceRef(loader="file", location=f"/{cid}")
    return RetrievedChunk(chunk=Chunk(id=cid, document_id="d", text=text, source_ref=ref), score=1.0)


def test_context_builder_formats_and_cites():
    built = DefaultContextBuilder(max_chars=100).build("q", [_rc("c1", "alpha"), _rc("c2", "beta")])

    assert built["context"] == "[1] alpha\n\n[2] beta"
    assert [c.chunk_id for c in built["citations"]] == ["c1", "c2"]
    assert built["citations"][0].source_ref.location == "/c1"


def test_context_builder_dedupes():
    built = DefaultContextBuilder(max_chars=100).build("q", [_rc("c1", "alpha"), _rc("c1", "alpha")])

    assert built["context"] == "[1] alpha"
    assert len(built["citations"]) == 1


def test_context_builder_respects_budget():
    built = DefaultContextBuilder(max_chars=5).build("q", [_rc("c1", "alpha"), _rc("c2", "beta")])

    assert built["context"] == "[1] alpha"
    assert len(built["citations"]) == 1
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_context_builder.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'rag_adapter.context.context_builder'`

- [ ] **Step 3: 實作 context_builder.py**

`rag_adapter/context/context_builder.py`:
```python
from rag_adapter.models import Citation


class DefaultContextBuilder:
    """依字元預算組裝 context:去重、加 [n] 來源標記、產出引用。"""

    def __init__(self, max_chars=6000):
        self._max_chars = max_chars

    def build(self, query, chunks):
        seen = set()
        parts = []
        citations = []
        used = 0
        for retrieved in chunks:
            chunk = retrieved.chunk
            if chunk.id in seen:
                continue
            seen.add(chunk.id)
            if parts and used + len(chunk.text) > self._max_chars:
                break
            parts.append(f"[{len(parts) + 1}] {chunk.text}")
            citations.append(Citation(chunk_id=chunk.id, source_ref=chunk.source_ref))
            used += len(chunk.text)
        return {"context": "\n\n".join(parts), "citations": citations}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_context_builder.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/context/context_builder.py tests/test_context_builder.py
git commit -m "feat: add default context builder"
```

---

## Task 8: config query schema + factory build_query_pipeline

**Files:**
- Modify: `rag_adapter/config.py`
- Modify: `rag_adapter/factory.py`
- Modify: `tests/test_config.py`、`tests/test_factory.py`

- [ ] **Step 1: 在 config.py 新增 query schema**

在 `rag_adapter/config.py` 的 `IndexingConfig` 定義之後、`RagConfig` 之前,插入:
```python
@dataclass(frozen=True)
class RetrieverConfig:
    type: str = "dense"
    top_k: int = 20

    def __post_init__(self) -> None:
        if self.top_k <= 0:
            raise ValueError("top_k must be greater than 0")


@dataclass(frozen=True)
class FusionConfig:
    type: str = "rrf"
    k: int = 60


@dataclass(frozen=True)
class RerankerConfig:
    type: str = "qwen"
    base_url: str = ""
    api_key: str = ""
    model: str = "qwen-reranker"


@dataclass(frozen=True)
class ContextConfig:
    max_chars: int = 6000

    def __post_init__(self) -> None:
        if self.max_chars <= 0:
            raise ValueError("max_chars must be greater than 0")


@dataclass(frozen=True)
class QueryConfig:
    retriever: RetrieverConfig = field(default_factory=RetrieverConfig)
    fusion: FusionConfig = field(default_factory=FusionConfig)
    reranker: RerankerConfig = field(default_factory=RerankerConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    top_k: int = 8

    def __post_init__(self) -> None:
        if self.top_k <= 0:
            raise ValueError("top_k must be greater than 0")
```
把 `RagConfig` 改為:
```python
@dataclass(frozen=True)
class RagConfig:
    indexing: IndexingConfig = field(default_factory=IndexingConfig)
    query: QueryConfig = field(default_factory=QueryConfig)
```
新增一個 query 轉換函式(放在 `_indexing_from_dict` 之後):
```python
def _query_from_dict(raw: dict) -> QueryConfig:
    return QueryConfig(
        retriever=RetrieverConfig(**raw.get("retriever", {})),
        fusion=FusionConfig(**raw.get("fusion", {})),
        reranker=RerankerConfig(**raw.get("reranker", {})),
        context=ContextConfig(**raw.get("context", {})),
        top_k=raw.get("top_k", 8),
    )
```
並把 `from_dict` 改為:
```python
def from_dict(raw: dict) -> RagConfig:
    """把已插值的 dict 轉成 typed RagConfig。"""
    return RagConfig(
        indexing=_indexing_from_dict(raw.get("indexing", {})),
        query=_query_from_dict(raw.get("query", {})),
    )
```

- [ ] **Step 2: 在 factory.py 新增 build_query_pipeline**

在 `rag_adapter/factory.py` 頂部 import 區補上:
```python
from rag_adapter.retrievers.dense_retriever import DenseRetriever
from rag_adapter.fusion.rrf_fusion import RRFFusion
from rag_adapter.rerankers.qwen_reranker import QwenReranker
from rag_adapter.context.context_builder import DefaultContextBuilder
from rag_adapter.pipeline.query import QueryPipeline
```
在檔尾追加:
```python
def _build_retriever(config, embedder, vector_store):
    if config.type == "dense":
        return DenseRetriever(embedder, vector_store)
    raise ValueError(f"unknown retriever type: {config.type}")


def _build_fusion(config):
    if config.type == "rrf":
        return RRFFusion(k=config.k)
    raise ValueError(f"unknown fusion type: {config.type}")


def _build_reranker(config):
    if config.type == "qwen":
        return QwenReranker(base_url=config.base_url, api_key=config.api_key, model=config.model)
    raise ValueError(f"unknown reranker type: {config.type}")


def build_query_pipeline(config):
    """依 RagConfig 組裝 QueryPipeline(到 retrieve_context 為止;生成屬 P4)。

    dense retriever 與 indexing 共用 embedder / vector store 設定。
    """
    embedder = _build_embedder(config.indexing.embedder)
    vector_store = _build_vector_store(config.indexing.vector_store)
    query = config.query
    return QueryPipeline(
        retrievers=[_build_retriever(query.retriever, embedder, vector_store)],
        fusion=_build_fusion(query.fusion),
        reranker=_build_reranker(query.reranker),
        context_builder=DefaultContextBuilder(max_chars=query.context.max_chars),
        top_k=query.top_k,
    )
```

- [ ] **Step 3: 更新 tests/test_config.py**

把 `_YAML` 字串(在 `vector_store` 區塊之後、結尾 `"""` 之前)補上 query 區塊:
```python
  vector_store:
    type: qdrant
    url: http://localhost:6333
    collection: docs
query:
  retriever:
    type: dense
    top_k: 30
  fusion:
    type: rrf
    k: 40
  reranker:
    type: qwen
    base_url: https://api/v1
    api_key: ${ENV:QWEN_KEY}
    model: qwen-reranker
  context:
    max_chars: 1234
  top_k: 5
"""
```
並在 `test_load_config_returns_typed_config_with_env_interpolation` 末端追加斷言:
```python
    assert config.query.retriever.top_k == 30
    assert config.query.fusion.k == 40
    assert config.query.reranker.api_key == "secret-123"
    assert config.query.context.max_chars == 1234
    assert config.query.top_k == 5
```

- [ ] **Step 4: 更新 tests/test_factory.py**

把 `tests/test_factory.py` 的 `_YAML` 同步補上與 Step 3 相同的 `query:` 區塊(置於 `vector_store` 之後),並新增測試:
```python
def test_build_query_pipeline_from_config(tmp_path, monkeypatch):
    monkeypatch.setenv("QWEN_KEY", "secret-123")
    cfg = tmp_path / "rag.yaml"
    cfg.write_text(textwrap.dedent(_YAML), encoding="utf-8")
    config = load_config(str(cfg))

    from rag_adapter.factory import build_query_pipeline
    from rag_adapter.retrievers.dense_retriever import DenseRetriever
    from rag_adapter.fusion.rrf_fusion import RRFFusion
    from rag_adapter.rerankers.qwen_reranker import QwenReranker
    from rag_adapter.context.context_builder import DefaultContextBuilder

    pipeline = build_query_pipeline(config)

    assert isinstance(pipeline._retrievers[0], DenseRetriever)
    assert isinstance(pipeline._fusion, RRFFusion)
    assert isinstance(pipeline._reranker, QwenReranker)
    assert isinstance(pipeline._context_builder, DefaultContextBuilder)
    assert pipeline._top_k == 5
```

- [ ] **Step 5: 跑測試**

Run: `pytest tests/test_config.py tests/test_factory.py -q`
Expected: PASS（全部 passed）

- [ ] **Step 6: Commit**

```bash
git add rag_adapter/config.py rag_adapter/factory.py tests/test_config.py tests/test_factory.py
git commit -m "feat: add query config schema and query pipeline factory"
```

---

## Task 9: Query 整合測試 + 全套件驗證

**Files:**
- Test: `tests/test_query_integration.py`

- [ ] **Step 1: 寫整合測試**

`tests/test_query_integration.py`(真實 DenseRetriever + RRFFusion + DefaultContextBuilder + 假 reranker,搭 in-memory store):
```python
from rag_adapter.models import Chunk
from rag_adapter.pipeline.query import QueryPipeline
from rag_adapter.retrievers.dense_retriever import DenseRetriever
from rag_adapter.fusion.rrf_fusion import RRFFusion
from rag_adapter.context.context_builder import DefaultContextBuilder
from rag_adapter.testing.mocks import EchoEmbedder, InMemoryVectorStore, NoopReranker


async def test_query_pipeline_retrieve_context_end_to_end():
    store = InMemoryVectorStore()
    await store.upsert([
        Chunk(id="c1", document_id="d", text="aa", embedding=[2.0]),
        Chunk(id="c2", document_id="d", text="aaaa", embedding=[4.0]),
    ])
    pipeline = QueryPipeline(
        retrievers=[DenseRetriever(EchoEmbedder(), store)],
        fusion=RRFFusion(),
        reranker=NoopReranker(),
        context_builder=DefaultContextBuilder(max_chars=1000),
        top_k=2,
    )

    built = await pipeline.retrieve_context("aaaa")

    assert "[1]" in built["context"]
    assert {c.chunk_id for c in built["citations"]} == {"c1", "c2"}
```

- [ ] **Step 2: 跑整合測試**

Run: `pytest tests/test_query_integration.py -q`
Expected: PASS（1 passed）

- [ ] **Step 3: 跑全部測試**

Run: `pytest -q`
Expected: PASS(P1/P2/P2.5 既有 35 + P3 新增,全部 passed)

- [ ] **Step 4: Commit**

```bash
git add tests/test_query_integration.py
git commit -m "test: add query pipeline retrieve_context integration"
```

---

## Self-Review

**Spec coverage(對照設計規格書 Query 區塊):**
- Retriever(cosine_similarity):DenseRetriever(Task 3)✓
- Retriever(BM25):BM25Retriever(Task 4)✓(config-driven hybrid 延後)
- Fusion(RRF):RRFFusion(Task 5)✓
- Reranker(Qwen):QwenReranker API(Task 6)✓
- ContextBuilder:DefaultContextBuilder(Task 7)✓
- QueryPipeline 端到端到 context:retrieve_context(Task 2)+ 整合測試(Task 9)✓
- Config-Driven query:config schema + build_query_pipeline(Task 8)✓
- 生成(PromptBuilder/Generator 真實實作)→ P4,本計畫刻意不含 ✓

**Async 邊界:** Retriever.retrieve / Reranker.rerank 為 async;Fusion.fuse / ContextBuilder.build 為 sync;pipeline 對應 await ✓

**Placeholder scan:** 無 TBD/TODO;每個 code step 皆含完整程式碼。

**一致性:** RetrievedChunk 流經 retriever→fusion→reranker→context;Citation 由 context builder 依 source_ref 產出;config 採 typed dataclass;factory 為 config 與實作的唯一橋樑。

---

## 後續(另開 docs)
- **P4 Generation**:PromptBuilder、Qwen Generator(async generate/stream),接上 QueryPipeline.answer/stream,擴充 config 的 generation 區塊
- **P5 Obs + Eval**:Langfuse trace、Retrieval 指標
```

