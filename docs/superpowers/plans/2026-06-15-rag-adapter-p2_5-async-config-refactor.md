# RAG Adapter — P2.5 Async + Config Refactor Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 把已完成的 P1/P2 重構為符合設計 pattern:**Async-First(僅 I/O 層)** 與 **Config-Driven(YAML)**,維持 Interface-Driven / Type-First(dataclass)/ Pipeline,並保留「最小型別註記」慣例。

**Architecture:** I/O 層 Protocol(Loader / Embedder / VectorStore / Retriever / Reranker / Generator)改 `async def`;純 CPU 層(Parser / Chunker / Fusion / ContextBuilder / PromptBuilder / QueryTransform)維持同步。Pipeline 於 I/O 步驟 `await`,`Generator.stream` 改 async generator。新增 `config.py`:讀 YAML(secrets 以 `${ENV:VAR}` 插值)→ provider 工廠 → 組裝 `IndexingPipeline`。

**Tech Stack:** Python 3.10+、asyncio、httpx.AsyncClient、qdrant-client AsyncQdrantClient、PyYAML、pytest + pytest-asyncio(`asyncio_mode=auto`)。

> 規格依據:`docs/superpowers/specs/2026-06-14-rag-adapter-design.md`(§7 Design Patterns)
> 決策:Async 僅套 I/O 層;型別維持最小註記(資料層 dataclass 即達標);先重構 P1/P2 再寫 P3–P5。
> 原子性:async 核心(interfaces + mocks + pipelines + FileLoader + 其測試 + 整合測試)在 Task 2 一次轉換,避免半轉換破測。其餘 provider 各自獨立轉。

---

## File Structure

```
pyproject.toml                       # 修改:pytest-asyncio、PyYAML、asyncio_mode
rag_adapter/
  interfaces.py                      # 修改:I/O 方法改 async
  testing/mocks.py                   # 修改:I/O mock 改 async
  pipeline/indexing.py               # 修改:async index
  pipeline/query.py                  # 修改:async answer/stream
  loaders/file_loader.py             # 修改:async load(asyncio.to_thread)
  loaders/http_loaders.py            # 修改:AsyncClient + async load
  embedders/qwen_embedder.py         # 修改:AsyncClient + async embed
  vectorstores/qdrant_store.py       # 修改:async upsert/delete/search
  config.py                          # 新增:YAML 載入 + provider 工廠
tests/                               # 多數 I/O 相關測試改 async;新增 test_config.py
```

不變(純 CPU,不需改):`models.py`、`parsers/*`、`chunkers/*` 與其測試 `test_models.py`、`test_html_parser.py`、`test_structured_parsers.py`、`test_character_chunker.py`。

---

## Task 1: 相依與 asyncio 設定

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 更新 pyproject.toml**

把 `dependencies` 與 `[project.optional-dependencies]` 與 `[tool.pytest.ini_options]` 改為:
```toml
dependencies = ["pyyaml>=6.0"]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "beautifulsoup4>=4.12", "httpx>=0.27", "qdrant-client>=1.9"]
html = ["beautifulsoup4>=4.12"]
http = ["httpx>=0.27"]
qdrant = ["qdrant-client>=1.9"]
all = ["beautifulsoup4>=4.12", "httpx>=0.27", "qdrant-client>=1.9"]
```
並把 `[tool.pytest.ini_options]` 區塊改為:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: 安裝並驗證**

Run: `pip install -e ".[dev]" && python -c "import yaml, pytest_asyncio; print('async deps ok')"`
Expected: 印出 `async deps ok`

- [ ] **Step 3: 確認既有測試在 auto 模式下仍綠**

Run: `pytest -q`
Expected: 29 passed(此時尚未改 async,全部仍同步)

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add pytest-asyncio and pyyaml, enable asyncio auto mode"
```

---

## Task 2: Async 核心(interfaces + mocks + pipelines + FileLoader + 測試)

**這是原子轉換**:以下檔案與測試一起改,改完整套測試需綠。

**Files:**
- Modify: `rag_adapter/interfaces.py`、`rag_adapter/testing/mocks.py`、`rag_adapter/pipeline/indexing.py`、`rag_adapter/pipeline/query.py`、`rag_adapter/loaders/file_loader.py`
- Modify (tests): `tests/test_indexing_pipeline.py`、`tests/test_query_pipeline.py`、`tests/test_file_loader.py`、`tests/test_indexing_integration.py`

- [ ] **Step 1: 改 interfaces.py(I/O 方法 async)**

`rag_adapter/interfaces.py` 全檔改為:
```python
from typing import Protocol, runtime_checkable

from rag_adapter.models import Document, Answer


@runtime_checkable
class Loader(Protocol):
    """取得原始 bytes / 連到資料來源,回傳尚未解析的原始 Document。"""
    async def load(self, location) -> list: ...


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
    async def embed(self, chunks: list) -> list: ...

    async def embed_query(self, text) -> list: ...


@runtime_checkable
class VectorStore(Protocol):
    """向量寫入 / 查詢,含 upsert / delete。"""
    async def upsert(self, chunks: list) -> None: ...

    async def delete(self, chunk_ids: list) -> None: ...

    async def search(self, embedding: list, top_k) -> list: ...


@runtime_checkable
class QueryTransform(Protocol):
    """查詢前處理(v1 僅 pass-through)。"""
    def transform(self, query) -> str: ...


@runtime_checkable
class Retriever(Protocol):
    """取回候選 RetrievedChunk。"""
    async def retrieve(self, query, top_k) -> list: ...


@runtime_checkable
class Fusion(Protocol):
    """合併多路檢索結果(如 RRF)。"""
    def fuse(self, ranked_lists: list, top_k) -> list: ...


@runtime_checkable
class Reranker(Protocol):
    """重排候選。"""
    async def rerank(self, query, candidates: list, top_k) -> list: ...


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
    """呼叫 LLM 生成答案。generate 為 async;stream 為 async generator。"""
    async def generate(self, prompt, citations: list) -> Answer: ...

    def stream(self, prompt, citations: list): ...
```

- [ ] **Step 2: 改 testing/mocks.py(I/O mock async)**

`rag_adapter/testing/mocks.py` 全檔改為:
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
    async def embed(self, chunks):
        for chunk in chunks:
            chunk.embedding = [float(len(chunk.text))]
        return chunks

    async def embed_query(self, text):
        return [float(len(text))]


class InMemoryVectorStore:
    def __init__(self):
        self._chunks = {}

    async def upsert(self, chunks):
        for chunk in chunks:
            self._chunks[chunk.id] = chunk

    async def delete(self, chunk_ids):
        for cid in chunk_ids:
            self._chunks.pop(cid, None)

    async def search(self, embedding, top_k):
        target = embedding[0]
        scored = []
        for chunk in self._chunks.values():
            if chunk.embedding is None:
                raise ValueError(f"chunk {chunk.id} has no embedding; embed before upsert")
            distance = abs(chunk.embedding[0] - target)
            scored.append(RetrievedChunk(chunk=chunk, score=-distance))
        scored.sort(key=lambda rc: rc.score, reverse=True)
        return scored[:top_k]


class VectorRetriever:
    """以 embedder + vector store 組成的簡單 retriever。"""
    def __init__(self, embedder, store):
        self._embedder = embedder
        self._store = store

    async def retrieve(self, query, top_k):
        embedding = await self._embedder.embed_query(query)
        return await self._store.search(embedding, top_k)


class PassthroughFusion:
    def fuse(self, ranked_lists, top_k):
        merged = [rc for ranked in ranked_lists for rc in ranked]
        merged.sort(key=lambda rc: rc.score, reverse=True)
        return merged[:top_k]


class NoopReranker:
    async def rerank(self, query, candidates, top_k):
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
    async def generate(self, prompt, citations):
        return Answer(text=f"ANSWER: {prompt}", citations=list(citations))

    async def stream(self, prompt, citations):
        for token in prompt.split():
            yield token
```

- [ ] **Step 3: 改 pipeline/indexing.py**

`rag_adapter/pipeline/indexing.py` 全檔改為:
```python
class IndexingPipeline:
    """依序執行 load → parse → chunk → embed → upsert。I/O 步驟以 await 執行。"""

    def __init__(self, loader, parser, chunker, embedder, vector_store):
        self._loader = loader
        self._parser = parser
        self._chunker = chunker
        self._embedder = embedder
        self._vector_store = vector_store

    async def index(self, location):
        documents = await self._loader.load(location)
        all_chunks = []
        for raw in documents:
            parsed = self._parser.parse(raw)
            all_chunks.extend(self._chunker.chunk(parsed))
        await self._embedder.embed(all_chunks)
        await self._vector_store.upsert(all_chunks)
        return len(all_chunks)
```

- [ ] **Step 4: 改 pipeline/query.py**

`rag_adapter/pipeline/query.py` 全檔改為:
```python
class QueryPipeline:
    """依序執行 (transform?) → retrieve(多路) → fuse → rerank → build context
    → build prompt → generate。I/O 步驟以 await 執行;stream 為 async generator。

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

    async def _prepare(self, query):
        if self._query_transform is not None:
            query = self._query_transform.transform(query)
        ranked_lists = []
        for retriever in self._retrievers:
            ranked_lists.append(await retriever.retrieve(query, self._top_k))
        fused = self._fusion.fuse(ranked_lists, self._top_k)
        reranked = await self._reranker.rerank(query, fused, self._top_k)
        built = self._context_builder.build(query, reranked)
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

- [ ] **Step 5: 改 loaders/file_loader.py**

`rag_adapter/loaders/file_loader.py` 全檔改為:
```python
import asyncio
from pathlib import Path

from rag_adapter.models import Document, SourceRef


class FileLoader:
    """從檔案路徑或目錄讀取原始內容(不解析)。目錄則遞迴讀取所有檔案。

    檔案讀取以 asyncio.to_thread 包起,避免阻塞事件迴圈。
    """

    def __init__(self, loader_name="file"):
        self._loader_name = loader_name

    async def load(self, location):
        documents = []
        for path in self._resolve(location):
            text = await asyncio.to_thread(path.read_text, encoding="utf-8")
            ref = SourceRef(loader=self._loader_name, location=str(path))
            documents.append(Document(id=str(path), text=text, source_ref=ref))
        return documents

    def _resolve(self, location):
        path = Path(location)
        if path.is_dir():
            return sorted(p for p in path.rglob("*") if p.is_file())
        return [path]
```

- [ ] **Step 6: 改 tests/test_indexing_pipeline.py**

`tests/test_indexing_pipeline.py` 全檔改為:
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
    async def load(self, location):
        return [
            Document(id="d1", text="aa"),
            Document(id="d2", text="aaaa"),
        ]


async def test_indexing_pipeline_indexes_documents_into_store():
    store = InMemoryVectorStore()
    pipeline = IndexingPipeline(
        loader=TwoDocLoader(),
        parser=PassthroughParser(),
        chunker=PassthroughChunker(),
        embedder=EchoEmbedder(),
        vector_store=store,
    )

    count = await pipeline.index("any-location")

    assert count == 2
    results = await store.search([4.0], top_k=1)
    assert results[0].chunk.document_id == "d2"
    assert results[0].chunk.embedding == [4.0]
```

- [ ] **Step 7: 改 tests/test_query_pipeline.py**

`tests/test_query_pipeline.py` 全檔改為:
```python
from rag_adapter.models import Document, Chunk
from rag_adapter.testing.mocks import (
    InMemoryVectorStore,
    EchoEmbedder,
    PassthroughChunker,
    PassthroughParser,
    VectorRetriever,
    PassthroughFusion,
    NoopReranker,
    SimpleContextBuilder,
    TemplatePromptBuilder,
    EchoGenerator,
)
from rag_adapter.pipeline.query import QueryPipeline


async def test_echo_embedder_fills_embedding():
    chunk = Chunk(id="c1", document_id="d1", text="ab")
    out = await EchoEmbedder().embed([chunk])
    assert out[0].embedding == [2.0]


async def test_vector_store_upsert_and_search():
    store = InMemoryVectorStore()
    c1 = Chunk(id="c1", document_id="d1", text="aa", embedding=[2.0])
    c2 = Chunk(id="c2", document_id="d1", text="aaaa", embedding=[4.0])
    await store.upsert([c1, c2])
    results = await store.search([4.0], top_k=1)
    assert results[0].chunk.id == "c2"


def test_passthrough_chunker_one_chunk_per_doc():
    doc = Document(id="d1", text="hello world")
    chunks = PassthroughChunker().chunk(doc)
    assert len(chunks) == 1
    assert chunks[0].document_id == "d1"
    assert chunks[0].text == "hello world"


def _build_store():
    store = InMemoryVectorStore()
    c1 = Chunk(id="c1", document_id="d1", text="aa", embedding=[2.0])
    c2 = Chunk(id="c2", document_id="d1", text="aaaa", embedding=[4.0])
    return store, [c1, c2]


def _build_pipeline(store):
    embedder = EchoEmbedder()
    return QueryPipeline(
        retrievers=[VectorRetriever(embedder, store)],
        fusion=PassthroughFusion(),
        reranker=NoopReranker(),
        context_builder=SimpleContextBuilder(),
        prompt_builder=TemplatePromptBuilder(),
        generator=EchoGenerator(),
        top_k=2,
    )


async def test_query_pipeline_returns_answer_with_citations():
    store, chunks = _build_store()
    await store.upsert(chunks)
    pipeline = _build_pipeline(store)

    answer = await pipeline.answer("aaaa")

    assert answer.text.startswith("ANSWER:")
    assert "aaaa" in answer.text
    citation_ids = [c.chunk_id for c in answer.citations]
    assert "c2" in citation_ids


async def test_query_pipeline_stream_yields_tokens():
    store, chunks = _build_store()
    await store.upsert(chunks)
    pipeline = _build_pipeline(store)

    tokens = [token async for token in pipeline.stream("aaaa")]

    assert len(tokens) > 0
    assert "Question:" in " ".join(tokens)


def test_public_exports():
    import rag_adapter

    assert hasattr(rag_adapter, "IndexingPipeline")
    assert hasattr(rag_adapter, "QueryPipeline")
    assert hasattr(rag_adapter, "Document")
    assert hasattr(rag_adapter, "Chunk")
    assert hasattr(rag_adapter, "Answer")
```

- [ ] **Step 8: 改 tests/test_file_loader.py**

`tests/test_file_loader.py` 全檔改為:
```python
from rag_adapter.loaders.file_loader import FileLoader


async def test_file_loader_reads_single_file(tmp_path):
    f = tmp_path / "a.html"
    f.write_text("<p>hi</p>", encoding="utf-8")

    docs = await FileLoader(loader_name="html").load(str(f))

    assert len(docs) == 1
    assert docs[0].text == "<p>hi</p>"
    assert docs[0].id == str(f)
    assert docs[0].source_ref.loader == "html"
    assert docs[0].source_ref.location == str(f)


async def test_file_loader_reads_directory_recursively(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_text("A", encoding="utf-8")
    (tmp_path / "sub" / "b.txt").write_text("B", encoding="utf-8")

    docs = await FileLoader().load(str(tmp_path))

    texts = sorted(d.text for d in docs)
    assert texts == ["A", "B"]
```

- [ ] **Step 9: 改 tests/test_indexing_integration.py**

`tests/test_indexing_integration.py` 全檔改為:
```python
from rag_adapter.pipeline.indexing import IndexingPipeline
from rag_adapter.loaders.file_loader import FileLoader
from rag_adapter.parsers.html_parser import HtmlParser
from rag_adapter.chunkers.character_chunker import CharacterChunker
from rag_adapter.testing.mocks import EchoEmbedder, InMemoryVectorStore


async def test_real_indexing_components_compose(tmp_path):
    page = tmp_path / "page.html"
    page.write_text(
        "<html><head><title>Doc</title></head><body><p>"
        + "word " * 50
        + "</p></body></html>",
        encoding="utf-8",
    )

    store = InMemoryVectorStore()
    pipeline = IndexingPipeline(
        loader=FileLoader(loader_name="html"),
        parser=HtmlParser(),
        chunker=CharacterChunker(chunk_size=80, chunk_overlap=10),
        embedder=EchoEmbedder(),
        vector_store=store,
    )

    count = await pipeline.index(str(page))

    assert count >= 2
    results = await store.search([80.0], top_k=1)
    assert results[0].chunk.document_id == str(page)
    assert results[0].chunk.source_ref.loader == "html"
    assert "title" in results[0].chunk.metadata
```

- [ ] **Step 10: 跑全部測試確認綠**

Run: `pytest -q`
Expected: PASS（http/qwen/qdrant 仍同步、其測試未改;async 核心已轉。全部 passed,數量與 Task 1 相同 29）

- [ ] **Step 11: Commit**

```bash
git add rag_adapter/interfaces.py rag_adapter/testing/mocks.py rag_adapter/pipeline/indexing.py rag_adapter/pipeline/query.py rag_adapter/loaders/file_loader.py tests/test_indexing_pipeline.py tests/test_query_pipeline.py tests/test_file_loader.py tests/test_indexing_integration.py
git commit -m "refactor: make core pipelines, mocks, and file loader async"
```

---

## Task 3: Async HTTP loaders

**Files:**
- Modify: `rag_adapter/loaders/http_loaders.py`
- Modify: `tests/test_http_loaders.py`

- [ ] **Step 1: 改 http_loaders.py**

`rag_adapter/loaders/http_loaders.py` 全檔改為:
```python
import httpx

from rag_adapter.models import Document, SourceRef


def _as_list(value):
    return [value] if isinstance(value, str) else list(value)


class UrlLoader:
    """以非同步 HTTP GET 抓取一或多個 URL 的原始內容(通常為 HTML),不解析。"""

    def __init__(self, client=None, loader_name="url"):
        self._client = client or httpx.AsyncClient(timeout=30)
        self._loader_name = loader_name

    async def load(self, location):
        documents = []
        for url in _as_list(location):
            response = await self._client.get(url)
            response.raise_for_status()
            ref = SourceRef(loader=self._loader_name, location=url)
            documents.append(Document(id=url, text=response.text, source_ref=ref))
        return documents


class TkmsLoader:
    """公司內部 wiki(TKMS)。目前以 HTML 處理:依 page id 組出 URL 非同步抓取。"""

    def __init__(self, base_url, client=None):
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=30)

    async def load(self, location):
        documents = []
        for page_id in _as_list(location):
            url = f"{self._base_url}/{page_id}"
            response = await self._client.get(url)
            response.raise_for_status()
            ref = SourceRef(loader="tkms", location=url)
            documents.append(Document(id=url, text=response.text, source_ref=ref))
        return documents
```

- [ ] **Step 2: 改 tests/test_http_loaders.py**

`tests/test_http_loaders.py` 全檔改為:
```python
from rag_adapter.loaders.http_loaders import UrlLoader, TkmsLoader


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class FakeHttpClient:
    def __init__(self, mapping):
        self._mapping = mapping
        self.requested = []

    async def get(self, url):
        self.requested.append(url)
        return FakeResponse(self._mapping[url])


async def test_url_loader_fetches_multiple_urls():
    client = FakeHttpClient({
        "http://a": "<p>A</p>",
        "http://b": "<p>B</p>",
    })
    docs = await UrlLoader(client=client).load(["http://a", "http://b"])

    assert [d.text for d in docs] == ["<p>A</p>", "<p>B</p>"]
    assert docs[0].id == "http://a"
    assert docs[0].source_ref.loader == "url"


async def test_tkms_loader_builds_page_urls():
    client = FakeHttpClient({"https://wiki/pages/42": "<p>wiki</p>"})
    docs = await TkmsLoader(base_url="https://wiki/pages/", client=client).load("42")

    assert client.requested == ["https://wiki/pages/42"]
    assert docs[0].text == "<p>wiki</p>"
    assert docs[0].source_ref.loader == "tkms"
    assert docs[0].source_ref.location == "https://wiki/pages/42"
```

- [ ] **Step 3: 跑測試**

Run: `pytest tests/test_http_loaders.py -q`
Expected: PASS（2 passed）

- [ ] **Step 4: Commit**

```bash
git add rag_adapter/loaders/http_loaders.py tests/test_http_loaders.py
git commit -m "refactor: make url and tkms loaders async"
```

---

## Task 4: Async Qwen embedder

**Files:**
- Modify: `rag_adapter/embedders/qwen_embedder.py`
- Modify: `tests/test_qwen_embedder.py`

- [ ] **Step 1: 改 qwen_embedder.py**

`rag_adapter/embedders/qwen_embedder.py` 全檔改為:
```python
import httpx


class QwenEmbedder:
    """以 OpenAI 相容的 /embeddings API 非同步取得向量(Qwen 模型)。"""

    def __init__(self, base_url, api_key, model, client=None, batch_size=16):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=60)
        self._batch_size = batch_size

    async def embed(self, chunks):
        vectors = await self._embed_texts([c.text for c in chunks])
        for chunk, vector in zip(chunks, vectors):
            chunk.embedding = vector
        return chunks

    async def embed_query(self, text):
        vectors = await self._embed_texts([text])
        return vectors[0]

    async def _embed_texts(self, texts):
        vectors = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start:start + self._batch_size]
            response = await self._client.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "input": batch},
            )
            response.raise_for_status()
            vectors.extend(item["embedding"] for item in response.json()["data"])
        return vectors
```

- [ ] **Step 2: 改 tests/test_qwen_embedder.py**

`tests/test_qwen_embedder.py` 全檔改為:
```python
from rag_adapter.models import Chunk
from rag_adapter.embedders.qwen_embedder import QwenEmbedder


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeHttpClient:
    def __init__(self, batches):
        self._batches = list(batches)
        self.calls = []

    async def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        vectors = self._batches.pop(0)
        return FakeResponse({"data": [{"embedding": v} for v in vectors]})


async def test_embed_fills_embeddings_and_batches():
    client = FakeHttpClient(batches=[[[1.0], [2.0]], [[3.0]]])
    embedder = QwenEmbedder(
        base_url="https://api/v1/",
        api_key="k",
        model="text-embedding-v3",
        client=client,
        batch_size=2,
    )
    chunks = [
        Chunk(id="c1", document_id="d", text="a"),
        Chunk(id="c2", document_id="d", text="b"),
        Chunk(id="c3", document_id="d", text="c"),
    ]

    out = await embedder.embed(chunks)

    assert [c.embedding for c in out] == [[1.0], [2.0], [3.0]]
    assert len(client.calls) == 2
    assert client.calls[0]["url"] == "https://api/v1/embeddings"
    assert client.calls[0]["headers"]["Authorization"] == "Bearer k"
    assert client.calls[0]["json"] == {"model": "text-embedding-v3", "input": ["a", "b"]}


async def test_embed_query_returns_single_vector():
    client = FakeHttpClient(batches=[[[9.0]]])
    embedder = QwenEmbedder(
        base_url="https://api/v1",
        api_key="k",
        model="m",
        client=client,
    )

    assert await embedder.embed_query("hello") == [9.0]
```

- [ ] **Step 3: 跑測試**

Run: `pytest tests/test_qwen_embedder.py -q`
Expected: PASS（2 passed）

- [ ] **Step 4: Commit**

```bash
git add rag_adapter/embedders/qwen_embedder.py tests/test_qwen_embedder.py
git commit -m "refactor: make qwen embedder async"
```

---

## Task 5: Async Qdrant vector store

**Files:**
- Modify: `rag_adapter/vectorstores/qdrant_store.py`
- Modify: `tests/test_qdrant_store.py`

- [ ] **Step 1: 改 qdrant_store.py**

只把 `upsert` / `delete` / `search` 改為 `async def` 並對 client 呼叫加 `await`;其餘不變。`rag_adapter/vectorstores/qdrant_store.py` 全檔改為:
```python
import uuid

from qdrant_client import models as qmodels

from rag_adapter.models import Chunk, RetrievedChunk, SourceRef


def _point_id(chunk_id):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


class QdrantVectorStore:
    """以 qdrant-client(AsyncQdrantClient)非同步儲存 / 查詢向量。

    chunk.id 以 uuid5 映成 point id,原始欄位存於 payload,search 時還原為 Chunk。
    collection 的建立與向量維度設定由呼叫端先行處理。
    """

    def __init__(self, client, collection):
        self._client = client
        self._collection = collection

    async def upsert(self, chunks):
        points = [
            qmodels.PointStruct(
                id=_point_id(chunk.id),
                vector=chunk.embedding,
                payload={
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "text": chunk.text,
                    "metadata": chunk.metadata,
                    "position": chunk.position,
                    "source_ref": self._dump_ref(chunk.source_ref),
                },
            )
            for chunk in chunks
        ]
        await self._client.upsert(collection_name=self._collection, points=points)

    async def delete(self, chunk_ids):
        await self._client.delete(
            collection_name=self._collection,
            points_selector=[_point_id(cid) for cid in chunk_ids],
        )

    async def search(self, embedding, top_k):
        hits = await self._client.search(
            collection_name=self._collection,
            query_vector=embedding,
            limit=top_k,
        )
        return [self._to_retrieved(hit) for hit in hits]

    def _to_retrieved(self, hit):
        payload = hit.payload
        chunk = Chunk(
            id=payload["chunk_id"],
            document_id=payload["document_id"],
            text=payload["text"],
            metadata=payload.get("metadata") or {},
            source_ref=self._load_ref(payload.get("source_ref")),
            position=payload.get("position") or {},
        )
        return RetrievedChunk(chunk=chunk, score=hit.score)

    def _dump_ref(self, ref):
        if ref is None:
            return None
        return {"loader": ref.loader, "location": ref.location, "position": ref.position}

    def _load_ref(self, data):
        if not data:
            return None
        return SourceRef(
            loader=data["loader"],
            location=data["location"],
            position=data.get("position") or {},
        )
```

- [ ] **Step 2: 改 tests/test_qdrant_store.py**

把 FakeQdrantClient 的方法改 async、測試改 async await。`tests/test_qdrant_store.py` 全檔改為:
```python
import uuid

from rag_adapter.models import Chunk, SourceRef
from rag_adapter.vectorstores.qdrant_store import QdrantVectorStore


class FakeHit:
    def __init__(self, payload, score):
        self.payload = payload
        self.score = score


class FakeQdrantClient:
    def __init__(self, hits=None):
        self.upserted = None
        self.deleted = None
        self.search_args = None
        self._hits = hits or []

    async def upsert(self, collection_name, points):
        self.upserted = {"collection": collection_name, "points": points}

    async def delete(self, collection_name, points_selector):
        self.deleted = {"collection": collection_name, "selector": points_selector}

    async def search(self, collection_name, query_vector, limit):
        self.search_args = {
            "collection": collection_name,
            "query_vector": query_vector,
            "limit": limit,
        }
        return self._hits


def _expected_point_id(chunk_id):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


async def test_upsert_maps_chunk_to_point_with_payload():
    client = FakeQdrantClient()
    store = QdrantVectorStore(client=client, collection="docs")
    chunk = Chunk(
        id="c1",
        document_id="d1",
        text="hello",
        metadata={"title": "T"},
        source_ref=SourceRef(loader="url", location="http://x"),
        embedding=[0.1, 0.2],
        position={"index": 0, "start": 0, "end": 5},
    )

    await store.upsert([chunk])

    point = client.upserted["points"][0]
    assert client.upserted["collection"] == "docs"
    assert point.id == _expected_point_id("c1")
    assert point.vector == [0.1, 0.2]
    assert point.payload["chunk_id"] == "c1"
    assert point.payload["text"] == "hello"
    assert point.payload["source_ref"] == {
        "loader": "url",
        "location": "http://x",
        "position": {},
    }


async def test_delete_maps_ids():
    client = FakeQdrantClient()
    store = QdrantVectorStore(client=client, collection="docs")

    await store.delete(["c1"])

    assert client.deleted["selector"] == [_expected_point_id("c1")]


async def test_search_reconstructs_retrieved_chunks():
    payload = {
        "chunk_id": "c1",
        "document_id": "d1",
        "text": "hello",
        "metadata": {"title": "T"},
        "position": {"index": 0, "start": 0, "end": 5},
        "source_ref": {"loader": "url", "location": "http://x", "position": {}},
    }
    client = FakeQdrantClient(hits=[FakeHit(payload, score=0.87)])
    store = QdrantVectorStore(client=client, collection="docs")

    results = await store.search([0.1, 0.2], top_k=3)

    assert client.search_args["limit"] == 3
    assert results[0].score == 0.87
    assert results[0].chunk.id == "c1"
    assert results[0].chunk.text == "hello"
    assert results[0].chunk.source_ref.loader == "url"
```

- [ ] **Step 3: 跑測試**

Run: `pytest tests/test_qdrant_store.py -q`
Expected: PASS（3 passed）

- [ ] **Step 4: Commit**

```bash
git add rag_adapter/vectorstores/qdrant_store.py tests/test_qdrant_store.py
git commit -m "refactor: make qdrant vector store async"
```

---

## Task 6: Config-Driven(YAML → provider 工廠 → IndexingPipeline)

**Files:**
- Create: `rag_adapter/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: 寫失敗測試**

`tests/test_config.py`:
```python
import textwrap

from rag_adapter.config import load_config, build_indexing_pipeline
from rag_adapter.loaders.file_loader import FileLoader
from rag_adapter.parsers.html_parser import HtmlParser
from rag_adapter.chunkers.character_chunker import CharacterChunker
from rag_adapter.embedders.qwen_embedder import QwenEmbedder
from rag_adapter.vectorstores.qdrant_store import QdrantVectorStore


_YAML = """
indexing:
  loader:
    type: file
    loader_name: html
  parser:
    type: html
  chunker:
    type: character
    chunk_size: 500
    chunk_overlap: 50
  embedder:
    type: qwen
    base_url: https://api/v1
    api_key: ${ENV:QWEN_KEY}
    model: text-embedding-v3
  vector_store:
    type: qdrant
    url: http://localhost:6333
    collection: docs
"""


def _write_cfg(tmp_path):
    cfg = tmp_path / "rag.yaml"
    cfg.write_text(textwrap.dedent(_YAML), encoding="utf-8")
    return str(cfg)


def test_load_config_interpolates_env(tmp_path, monkeypatch):
    monkeypatch.setenv("QWEN_KEY", "secret-123")

    config = load_config(_write_cfg(tmp_path))

    assert config["indexing"]["embedder"]["api_key"] == "secret-123"


def test_build_indexing_pipeline_from_config(tmp_path, monkeypatch):
    monkeypatch.setenv("QWEN_KEY", "secret-123")
    config = load_config(_write_cfg(tmp_path))

    pipeline = build_indexing_pipeline(config)

    assert isinstance(pipeline._loader, FileLoader)
    assert isinstance(pipeline._parser, HtmlParser)
    assert isinstance(pipeline._chunker, CharacterChunker)
    assert isinstance(pipeline._embedder, QwenEmbedder)
    assert isinstance(pipeline._vector_store, QdrantVectorStore)
    assert pipeline._embedder._api_key == "secret-123"
    assert pipeline._chunker._chunk_size == 500
    assert pipeline._vector_store._collection == "docs"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_config.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'rag_adapter.config'`

- [ ] **Step 3: 實作 config.py**

`rag_adapter/config.py`:
```python
import os
import re

import yaml

from rag_adapter.loaders.file_loader import FileLoader
from rag_adapter.loaders.http_loaders import UrlLoader, TkmsLoader
from rag_adapter.parsers.html_parser import HtmlParser
from rag_adapter.parsers.structured_parsers import JsonParser, XmlParser
from rag_adapter.chunkers.character_chunker import CharacterChunker
from rag_adapter.embedders.qwen_embedder import QwenEmbedder
from rag_adapter.vectorstores.qdrant_store import QdrantVectorStore
from rag_adapter.pipeline.indexing import IndexingPipeline


_ENV_PATTERN = re.compile(r"\$\{ENV:([^}]+)\}")


def _interpolate(value):
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: os.environ[m.group(1)], value)
    if isinstance(value, dict):
        return {key: _interpolate(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_interpolate(item) for item in value]
    return value


def load_config(path):
    """讀取 YAML 配置,並把 ${ENV:VAR} 以環境變數插值。"""
    with open(path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return _interpolate(raw)


def _build_loader(spec):
    spec = dict(spec)
    kind = spec.pop("type")
    if kind == "file":
        return FileLoader(**spec)
    if kind == "url":
        return UrlLoader(**spec)
    if kind == "tkms":
        return TkmsLoader(**spec)
    raise ValueError(f"unknown loader type: {kind}")


def _build_parser(spec):
    kind = spec["type"]
    if kind == "html":
        return HtmlParser()
    if kind == "json":
        return JsonParser()
    if kind == "xml":
        return XmlParser()
    raise ValueError(f"unknown parser type: {kind}")


def _build_chunker(spec):
    spec = dict(spec)
    kind = spec.pop("type")
    if kind == "character":
        return CharacterChunker(**spec)
    raise ValueError(f"unknown chunker type: {kind}")


def _build_embedder(spec):
    spec = dict(spec)
    kind = spec.pop("type")
    if kind == "qwen":
        return QwenEmbedder(**spec)
    raise ValueError(f"unknown embedder type: {kind}")


def _build_vector_store(spec):
    spec = dict(spec)
    kind = spec.pop("type")
    if kind == "qdrant":
        from qdrant_client import AsyncQdrantClient

        url = spec.pop("url")
        collection = spec.pop("collection")
        return QdrantVectorStore(client=AsyncQdrantClient(url=url), collection=collection)
    raise ValueError(f"unknown vector store type: {kind}")


def build_indexing_pipeline(config):
    """依 config 的 indexing 區塊組裝 IndexingPipeline。"""
    indexing = config["indexing"]
    return IndexingPipeline(
        loader=_build_loader(indexing["loader"]),
        parser=_build_parser(indexing["parser"]),
        chunker=_build_chunker(indexing["chunker"]),
        embedder=_build_embedder(indexing["embedder"]),
        vector_store=_build_vector_store(indexing["vector_store"]),
    )
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_config.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/config.py tests/test_config.py
git commit -m "feat: add yaml config-driven indexing pipeline factory"
```

---

## Task 7: 全套件驗證

- [ ] **Step 1: 跑全部測試**

Run: `pytest -q`
Expected: PASS（P1/P2 既有 29 + config 新增 2 = 31,全部 passed;async 測試由 asyncio_mode=auto 驅動）

- [ ] **Step 2(若有 README/範例需更新則一併,否則略過)**

本計畫不含文件;若有 example 需改為 `asyncio.run(pipeline.index(...))` 則另行處理。

---

## Self-Review

**Pattern coverage(對照設計規格書 §7):**
- Interface-Driven:Protocol 仍為骨架(I/O 方法改 async)✓
- Type-First:資料層 dataclass 不變;維持最小型別註記 ✓
- Async-First(I/O 層):Loader/Embedder/VectorStore/Retriever/Reranker/Generator 全 async;Parser/Chunker/Fusion/ContextBuilder/PromptBuilder/QueryTransform 維持同步;pipeline await;stream 為 async generator ✓
- Config-Driven:`config.py` YAML + env 插值 + provider 工廠 + build_indexing_pipeline ✓
- Pipeline:不變 ✓

**Placeholder scan:** 無 TBD/TODO;每個 code step 皆含完整程式碼。

**一致性檢查:**
- async 邊界:CPU 層方法(parse/chunk/fuse/build/build_prompt/transform)在 pipeline 中**不** await;I/O 層方法(load/embed/upsert/search/retrieve/rerank/generate/stream)**有** await。
- 測試:I/O 相關測試與假 client 全 async;純 CPU 測試(parsers/chunker/passthrough chunker)維持同步。
- 原子性:Task 2 一次轉換 async 核心(含整合測試),避免半同步破測;其餘 provider 各自獨立轉,逐 task 綠。

---

## 後續(沿用新標準,另開 docs)
- **P3 Query**:cosine/BM25 Retriever(async)、RRF Fusion(sync)、Qwen Reranker(async)、ContextBuilder(sync)、並擴充 config 的 query 區塊
- **P4 Generation**:PromptBuilder(sync)、Qwen Generator(async generate/stream)
- **P5 Obs + Eval**:Langfuse trace、Retrieval 指標
```

