# RAG Adapter — P1 Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 RAG Adapter SDK 的地基:統一的 Document/Chunk 資料模型、全部分層 `Protocol` 介面,以及用 mock 實作即可端到端跑通的 IndexingPipeline / QueryPipeline。

**Architecture:** 各層以 `typing.Protocol` 定義結構型介面,pipeline 透過建構式依賴注入組裝。資料模型(dataclass)是貫穿全程的契約。本計畫不接任何真實 provider,改用 in-memory mock 證明「可替換」架構成立並端到端跑通(含 generation)。

**Tech Stack:** Python 3.10+、dataclasses、`typing.Protocol`、pytest。

> 規格依據:`docs/superpowers/specs/2026-06-14-rag-adapter-design.md`(spec 保留不動,本文件僅承載實作細節)
> 型別註記慣例:函式簽章僅在必要時標註 `dict` / `list`,不引入額外 `typing` 匯入(`Protocol` 為結構必要除外),不標註基本型別;dataclass 欄位的型別宣告為語言必要,照常書寫。

---

## File Structure

本計畫建立的檔案(整個 SDK 的骨架):

```
pyproject.toml                       # 套件設定
rag_adapter/
  __init__.py                        # 對外匯出
  models.py                          # Document / Chunk / RetrievedChunk / Citation / Answer
  interfaces.py                      # 全部分層 Protocol
  pipeline/
    __init__.py
    indexing.py                      # IndexingPipeline
    query.py                         # QueryPipeline
  testing/
    __init__.py
    mocks.py                         # 各 Protocol 的 in-memory mock 實作(供測試與 quick-start 示範)
tests/
  test_models.py
  test_indexing_pipeline.py
  test_query_pipeline.py
```

責任邊界:
- `models.py` 只放資料結構,無行為依賴。
- `interfaces.py` 只放 Protocol,無實作。
- `pipeline/indexing.py`、`pipeline/query.py` 各只負責「依序呼叫注入的各層」,不含任何 provider 邏輯。
- `testing/mocks.py` 提供最小可用的假實作,讓 pipeline 不需真實 provider 即可測試。

---

## Task 1: 專案骨架

**Files:**
- Create: `pyproject.toml`
- Create: `rag_adapter/__init__.py`
- Create: `rag_adapter/pipeline/__init__.py`
- Create: `rag_adapter/testing/__init__.py`

- [ ] **Step 1: 建立 pyproject.toml**

```toml
[project]
name = "rag-adapter"
version = "0.1.0"
description = "Replaceable RAG pipeline adapter SDK"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["rag_adapter*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: 建立空的 package 檔**

`rag_adapter/__init__.py`:
```python
__version__ = "0.1.0"
```

`rag_adapter/pipeline/__init__.py`:
```python
```

`rag_adapter/testing/__init__.py`:
```python
```

- [ ] **Step 3: 安裝並驗證可匯入**

Run: `pip install -e ".[dev]" && python -c "import rag_adapter; print(rag_adapter.__version__)"`
Expected: 印出 `0.1.0`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml rag_adapter/__init__.py rag_adapter/pipeline/__init__.py rag_adapter/testing/__init__.py
git commit -m "chore: scaffold rag_adapter package"
```

---

## Task 2: 資料模型(Document / Chunk / RetrievedChunk / Citation / Answer)

**Files:**
- Create: `rag_adapter/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: 寫失敗測試**

`tests/test_models.py`:
```python
from rag_adapter.models import (
    SourceRef,
    Document,
    Chunk,
    RetrievedChunk,
    Citation,
    Answer,
)


def test_document_defaults():
    doc = Document(id="d1", text="hello")
    assert doc.id == "d1"
    assert doc.text == "hello"
    assert doc.metadata == {}
    assert doc.source_ref is None


def test_chunk_carries_source_ref_and_embedding():
    ref = SourceRef(loader="html", location="http://x")
    chunk = Chunk(
        id="c1",
        document_id="d1",
        text="part",
        source_ref=ref,
        embedding=[0.1, 0.2],
    )
    assert chunk.document_id == "d1"
    assert chunk.source_ref.loader == "html"
    assert chunk.embedding == [0.1, 0.2]
    assert chunk.metadata == {}


def test_retrieved_chunk_has_score():
    chunk = Chunk(id="c1", document_id="d1", text="part")
    rc = RetrievedChunk(chunk=chunk, score=0.9)
    assert rc.chunk.id == "c1"
    assert rc.score == 0.9


def test_answer_holds_citations():
    ref = SourceRef(loader="html", location="http://x")
    cit = Citation(chunk_id="c1", source_ref=ref)
    answer = Answer(text="result", citations=[cit])
    assert answer.text == "result"
    assert answer.citations[0].chunk_id == "c1"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_models.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'rag_adapter.models'`

- [ ] **Step 3: 實作 models.py**

`rag_adapter/models.py`:
```python
from dataclasses import dataclass, field


@dataclass
class SourceRef:
    """指回原始來源,供引用與可追溯使用。"""
    loader: str
    location: str
    position: dict = field(default_factory=dict)


@dataclass
class Document:
    """Loader/Parser 產出的整份文件。"""
    id: str
    text: str
    metadata: dict = field(default_factory=dict)
    source_ref: SourceRef = None


@dataclass
class Chunk:
    """Chunker 切出的片段,貫穿 embedding/retrieval/context。"""
    id: str
    document_id: str
    text: str
    metadata: dict = field(default_factory=dict)
    source_ref: SourceRef = None
    embedding: list = None
    position: dict = field(default_factory=dict)


@dataclass
class RetrievedChunk:
    """檢索/重排後帶分數的片段。"""
    chunk: Chunk
    score: float


@dataclass
class Citation:
    """ContextBuilder/Generator 產出的引用。"""
    chunk_id: str
    source_ref: SourceRef


@dataclass
class Answer:
    """Generator 的最終輸出。"""
    text: str
    citations: list = field(default_factory=list)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_models.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/models.py tests/test_models.py
git commit -m "feat: add core document/chunk data model"
```

---

## Task 3: 分層 Protocol 介面

**Files:**
- Create: `rag_adapter/interfaces.py`
- Test: `tests/test_models.py`(沿用,加一個 import 健全性測試)

- [ ] **Step 1: 寫失敗測試(確認介面可匯入)**

在 `tests/test_models.py` 末端新增:
```python
def test_interfaces_are_importable():
    from rag_adapter import interfaces

    expected = [
        "Loader",
        "Parser",
        "Chunker",
        "Embedder",
        "VectorStore",
        "QueryTransform",
        "Retriever",
        "Fusion",
        "Reranker",
        "ContextBuilder",
        "PromptBuilder",
        "Generator",
    ]
    for name in expected:
        assert hasattr(interfaces, name), name
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_models.py::test_interfaces_are_importable -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'rag_adapter.interfaces'`

- [ ] **Step 3: 實作 interfaces.py**

`rag_adapter/interfaces.py`:
```python
from typing import Protocol, runtime_checkable

from rag_adapter.models import Document, Answer


@runtime_checkable
class Loader(Protocol):
    """取得原始 bytes / 連到資料來源,回傳尚未解析的原始 Document。"""
    def load(self, location) -> list: ...


@runtime_checkable
class Parser(Protocol):
    """從格式抽出乾淨文字與 metadata。"""
    def parse(self, document: Document) -> Document: ...


@runtime_checkable
class Chunker(Protocol):
    """把 Document 切成 Chunk。"""
    def chunk(self, document: Document) -> list: ...


@runtime_checkable
class Embedder(Protocol):
    """文字 → 向量;就地填入 chunk.embedding 並回傳。"""
    def embed(self, chunks: list) -> list: ...

    def embed_query(self, text) -> list: ...


@runtime_checkable
class VectorStore(Protocol):
    """向量寫入 / 查詢,含 upsert / delete。"""
    def upsert(self, chunks: list) -> None: ...

    def delete(self, chunk_ids: list) -> None: ...

    def search(self, embedding: list, top_k) -> list: ...


@runtime_checkable
class QueryTransform(Protocol):
    """查詢前處理(v1 僅 pass-through)。"""
    def transform(self, query) -> str: ...


@runtime_checkable
class Retriever(Protocol):
    """取回候選 RetrievedChunk。"""
    def retrieve(self, query, top_k) -> list: ...


@runtime_checkable
class Fusion(Protocol):
    """合併多路檢索結果(如 RRF)。"""
    def fuse(self, ranked_lists: list, top_k) -> list: ...


@runtime_checkable
class Reranker(Protocol):
    """重排候選。"""
    def rerank(self, query, candidates: list, top_k) -> list: ...


@runtime_checkable
class ContextBuilder(Protocol):
    """去重 / token 預算 / 組裝 context,產出 context 字串與引用。"""
    def build(self, query, chunks: list) -> dict: ...


@runtime_checkable
class PromptBuilder(Protocol):
    """以 template 把 query + context 組成 prompt。"""
    def build_prompt(self, query, context) -> str: ...


@runtime_checkable
class Generator(Protocol):
    """呼叫 LLM 生成答案。"""
    def generate(self, prompt, citations: list) -> Answer: ...

    def stream(self, prompt, citations: list): ...
```

> 介面約定:
> - `Embedder.embed` 就地填 `chunk.embedding` 並回傳同一批 chunks。
> - `VectorStore.search` 回傳 `list[RetrievedChunk]`。
> - `Retriever.retrieve` 回傳 `list[RetrievedChunk]`。
> - `ContextBuilder.build` 回傳 `dict`,鍵為 `"context"`(str)與 `"citations"`(list[Citation])。
> - `Generator.generate` 回傳 `Answer`;`Generator.stream` 回傳逐段字串的 iterator。

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_models.py -v`
Expected: PASS（全部 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/interfaces.py tests/test_models.py
git commit -m "feat: add layered protocol interfaces"
```

---

## Task 4: in-memory mock 實作(供 pipeline 測試)

**Files:**
- Create: `rag_adapter/testing/mocks.py`
- Test: `tests/test_query_pipeline.py`

- [ ] **Step 1: 寫失敗測試**

`tests/test_query_pipeline.py`:
```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_query_pipeline.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'rag_adapter.testing.mocks'`

- [ ] **Step 3: 實作 mocks.py**

`rag_adapter/testing/mocks.py`:
```python
from rag_adapter.models import Chunk, RetrievedChunk, Citation, Answer


class PassthroughParser:
    def parse(self, document):
        return document


class PassthroughChunker:
    def chunk(self, document):
        chunk = Chunk(
            id=f"{document.id}-0",
            document_id=document.id,
            text=document.text,
            metadata=dict(document.metadata),
            source_ref=document.source_ref,
        )
        return [chunk]


class EchoEmbedder:
    """以文字長度當作 1 維向量,方便確定性測試。"""
    def embed(self, chunks):
        for chunk in chunks:
            chunk.embedding = [float(len(chunk.text))]
        return chunks

    def embed_query(self, text):
        return [float(len(text))]


class InMemoryVectorStore:
    def __init__(self):
        self._chunks = {}

    def upsert(self, chunks):
        for chunk in chunks:
            self._chunks[chunk.id] = chunk

    def delete(self, chunk_ids):
        for cid in chunk_ids:
            self._chunks.pop(cid, None)

    def search(self, embedding, top_k):
        target = embedding[0]
        scored = []
        for chunk in self._chunks.values():
            distance = abs(chunk.embedding[0] - target)
            scored.append(RetrievedChunk(chunk=chunk, score=-distance))
        scored.sort(key=lambda rc: rc.score, reverse=True)
        return scored[:top_k]


class VectorRetriever:
    """以 embedder + vector store 組成的簡單 retriever。"""
    def __init__(self, embedder, store):
        self._embedder = embedder
        self._store = store

    def retrieve(self, query, top_k):
        embedding = self._embedder.embed_query(query)
        return self._store.search(embedding, top_k)


class PassthroughFusion:
    def fuse(self, ranked_lists, top_k):
        merged = [rc for ranked in ranked_lists for rc in ranked]
        merged.sort(key=lambda rc: rc.score, reverse=True)
        return merged[:top_k]


class NoopReranker:
    def rerank(self, query, candidates, top_k):
        return candidates[:top_k]


class SimpleContextBuilder:
    def build(self, query, chunks):
        context = "\n".join(rc.chunk.text for rc in chunks)
        citations = [
            Citation(chunk_id=rc.chunk.id, source_ref=rc.chunk.source_ref)
            for rc in chunks
        ]
        return {"context": context, "citations": citations}


class TemplatePromptBuilder:
    def build_prompt(self, query, context):
        return f"Context:\n{context}\n\nQuestion: {query}"


class EchoGenerator:
    """把 prompt 前綴回去,作為確定性的假 LLM。"""
    def generate(self, prompt, citations):
        return Answer(text=f"ANSWER: {prompt}", citations=list(citations))

    def stream(self, prompt, citations):
        for token in prompt.split():
            yield token
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_query_pipeline.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/testing/mocks.py tests/test_query_pipeline.py
git commit -m "feat: add in-memory mocks for pipeline testing"
```

---

## Task 5: IndexingPipeline

**Files:**
- Create: `rag_adapter/pipeline/indexing.py`
- Test: `tests/test_indexing_pipeline.py`

- [ ] **Step 1: 寫失敗測試**

`tests/test_indexing_pipeline.py`:
```python
from rag_adapter.models import Document
from rag_adapter.pipeline.indexing import IndexingPipeline
from rag_adapter.testing.mocks import (
    PassthroughParser,
    PassthroughChunker,
    EchoEmbedder,
    InMemoryVectorStore,
)


class TwoDocLoader:
    def load(self, location):
        return [
            Document(id="d1", text="aa"),
            Document(id="d2", text="aaaa"),
        ]


def test_indexing_pipeline_indexes_documents_into_store():
    store = InMemoryVectorStore()
    pipeline = IndexingPipeline(
        loader=TwoDocLoader(),
        parser=PassthroughParser(),
        chunker=PassthroughChunker(),
        embedder=EchoEmbedder(),
        vector_store=store,
    )

    count = pipeline.index("any-location")

    assert count == 2
    results = store.search([4.0], top_k=1)
    assert results[0].chunk.document_id == "d2"
    assert results[0].chunk.embedding == [4.0]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_indexing_pipeline.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'rag_adapter.pipeline.indexing'`

- [ ] **Step 3: 實作 indexing.py**

`rag_adapter/pipeline/indexing.py`:
```python
class IndexingPipeline:
    """依序執行 load → parse → chunk → embed → upsert。各層皆為注入的 Protocol 實作。"""

    def __init__(self, loader, parser, chunker, embedder, vector_store):
        self._loader = loader
        self._parser = parser
        self._chunker = chunker
        self._embedder = embedder
        self._vector_store = vector_store

    def index(self, location):
        documents = self._loader.load(location)
        all_chunks = []
        for raw in documents:
            parsed = self._parser.parse(raw)
            all_chunks.extend(self._chunker.chunk(parsed))
        self._embedder.embed(all_chunks)
        self._vector_store.upsert(all_chunks)
        return len(all_chunks)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_indexing_pipeline.py -v`
Expected: PASS（1 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/pipeline/indexing.py tests/test_indexing_pipeline.py
git commit -m "feat: add indexing pipeline orchestrator"
```

---

## Task 6: QueryPipeline(端到端到答案生成)

**Files:**
- Create: `rag_adapter/pipeline/query.py`
- Test: `tests/test_query_pipeline.py`(沿用,新增端到端測試)

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_query_pipeline.py` 末端新增:
```python
from rag_adapter.pipeline.query import QueryPipeline
from rag_adapter.testing.mocks import (
    VectorRetriever,
    PassthroughFusion,
    NoopReranker,
    SimpleContextBuilder,
    TemplatePromptBuilder,
    EchoGenerator,
)


def _build_store():
    store = InMemoryVectorStore()
    c1 = Chunk(id="c1", document_id="d1", text="aa", embedding=[2.0])
    c2 = Chunk(id="c2", document_id="d1", text="aaaa", embedding=[4.0])
    store.upsert([c1, c2])
    return store


def test_query_pipeline_returns_answer_with_citations():
    store = _build_store()
    embedder = EchoEmbedder()
    pipeline = QueryPipeline(
        retrievers=[VectorRetriever(embedder, store)],
        fusion=PassthroughFusion(),
        reranker=NoopReranker(),
        context_builder=SimpleContextBuilder(),
        prompt_builder=TemplatePromptBuilder(),
        generator=EchoGenerator(),
        top_k=2,
    )

    answer = pipeline.answer("aaaa")

    assert answer.text.startswith("ANSWER:")
    assert "aaaa" in answer.text
    citation_ids = [c.chunk_id for c in answer.citations]
    assert "c2" in citation_ids


def test_query_pipeline_stream_yields_tokens():
    store = _build_store()
    embedder = EchoEmbedder()
    pipeline = QueryPipeline(
        retrievers=[VectorRetriever(embedder, store)],
        fusion=PassthroughFusion(),
        reranker=NoopReranker(),
        context_builder=SimpleContextBuilder(),
        prompt_builder=TemplatePromptBuilder(),
        generator=EchoGenerator(),
        top_k=2,
    )

    tokens = list(pipeline.stream("aaaa"))

    assert len(tokens) > 0
    assert "Question:" in " ".join(tokens)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_query_pipeline.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'rag_adapter.pipeline.query'`

- [ ] **Step 3: 實作 query.py**

`rag_adapter/pipeline/query.py`:
```python
class QueryPipeline:
    """依序執行 (transform?) → retrieve(多路) → fuse → rerank → build context
    → build prompt → generate。各層皆為注入的 Protocol 實作。

    query_transform 為可選;傳入 None 時跳過。
    """

    def __init__(
        self,
        retrievers,
        fusion,
        reranker,
        context_builder,
        prompt_builder,
        generator,
        top_k,
        query_transform=None,
    ):
        self._retrievers = retrievers
        self._fusion = fusion
        self._reranker = reranker
        self._context_builder = context_builder
        self._prompt_builder = prompt_builder
        self._generator = generator
        self._top_k = top_k
        self._query_transform = query_transform

    def _prepare(self, query):
        if self._query_transform is not None:
            query = self._query_transform.transform(query)
        ranked_lists = [r.retrieve(query, self._top_k) for r in self._retrievers]
        fused = self._fusion.fuse(ranked_lists, self._top_k)
        reranked = self._reranker.rerank(query, fused, self._top_k)
        built = self._context_builder.build(query, reranked)
        prompt = self._prompt_builder.build_prompt(query, built["context"])
        return prompt, built["citations"]

    def answer(self, query):
        prompt, citations = self._prepare(query)
        return self._generator.generate(prompt, citations)

    def stream(self, query):
        prompt, citations = self._prepare(query)
        return self._generator.stream(prompt, citations)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_query_pipeline.py -v`
Expected: PASS（全部 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/pipeline/query.py tests/test_query_pipeline.py
git commit -m "feat: add query pipeline orchestrator with generation"
```

---

## Task 7: 對外匯出與整體煙霧測試

**Files:**
- Modify: `rag_adapter/__init__.py`
- Test: `tests/test_query_pipeline.py`(沿用)

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_query_pipeline.py` 末端新增:
```python
def test_public_exports():
    import rag_adapter

    assert hasattr(rag_adapter, "IndexingPipeline")
    assert hasattr(rag_adapter, "QueryPipeline")
    assert hasattr(rag_adapter, "Document")
    assert hasattr(rag_adapter, "Chunk")
    assert hasattr(rag_adapter, "Answer")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_query_pipeline.py::test_public_exports -v`
Expected: FAIL，`AttributeError: module 'rag_adapter' has no attribute 'IndexingPipeline'`

- [ ] **Step 3: 更新 __init__.py**

`rag_adapter/__init__.py`:
```python
from rag_adapter.models import (
    SourceRef,
    Document,
    Chunk,
    RetrievedChunk,
    Citation,
    Answer,
)
from rag_adapter.pipeline.indexing import IndexingPipeline
from rag_adapter.pipeline.query import QueryPipeline

__version__ = "0.1.0"

__all__ = [
    "SourceRef",
    "Document",
    "Chunk",
    "RetrievedChunk",
    "Citation",
    "Answer",
    "IndexingPipeline",
    "QueryPipeline",
]
```

- [ ] **Step 4: 跑全部測試確認通過**

Run: `pytest -v`
Expected: PASS（全部 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/__init__.py tests/test_query_pipeline.py
git commit -m "feat: expose public api surface"
```

---

## Self-Review

**Spec coverage(對照 `2026-06-14-rag-adapter-design.md`):**
- Replaceable:全部分層 Protocol(Task 3)+ DI 組裝(Task 5/6)✓
- Document/Chunk 資料模型:Task 2 ✓
- Fusion 層:介面(Task 3)+ mock 實作與接線(Task 4/6)✓
- VectorStore upsert/delete:介面(Task 3)+ mock(Task 4)✓
- QueryTransform 可選預留:介面(Task 3)+ pipeline 可選參數(Task 6)✓
- PromptBuilder + Generator(generate/stream):介面(Task 3)+ mock + 端到端(Task 4/6)✓
- Quick-Start 端到端到答案:Task 6 端到端測試 ✓
- 真實 provider(Qwen/Qdrant/html 等)→ 屬 P2–P4,本計畫刻意不含 ✓
- Observability / Evaluation → 屬 P5,本計畫不含 ✓

**Placeholder scan:** 無 TBD / TODO;每個 code step 皆含完整程式碼。

**Type consistency:** `ContextBuilder.build` 一律回傳 `{"context", "citations"}`;`Generator.generate` 回 `Answer`、`stream` 為 iterator;retriever/store/fusion/reranker 一律處理 `list[RetrievedChunk]`。各 Task 簽章一致。

---

## 後續計畫(待 P1 確認後另開 docs)
- **P2 Indexing**:html/tkms/json/xml Loader、Parser、Chunker、Qwen Embedder、Qdrant VectorStore
- **P3 Query**:cosine/BM25 Retriever、RRF Fusion、Qwen Reranker、ContextBuilder
- **P4 Generation**:PromptBuilder、Qwen Generator(generate/stream)
- **P5 Obs + Eval**:Langfuse trace、Retrieval 指標(recall@k/precision@k/MRR/nDCG)
```

