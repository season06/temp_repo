# RAG Adapter — P2 Indexing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 為 Indexing pipeline 補上真實 provider 實作:來源 Loader(File / URL / TKMS-wiki)、格式 Parser(HTML / JSON / XML)、CharacterChunker、Qwen Embedder(API)、Qdrant VectorStore(client),並以整合測試證明它們能與 P1 的 `IndexingPipeline` 組裝。

**Architecture:** 沿用 P1 的 `Protocol` 介面與 Document/Chunk 資料模型。**Loader 負責「取得來源」**(file/url/wiki),**Parser 負責「依格式抽取乾淨文字」**(html/json/xml),兩者解耦。外部相依(httpx、qdrant-client)以建構式注入 client,使單元測試完全不需網路或真實服務。

**Tech Stack:** Python 3.10+、beautifulsoup4(HTML)、httpx(HTTP + Qwen API)、qdrant-client、stdlib json / xml.etree、pytest。

> 規格依據:`docs/superpowers/specs/2026-06-14-rag-adapter-design.md`
> Provider 決策:tkms=內部 wiki 以 HTML 處理;Qwen 走 OpenAI 相容 `/embeddings` API;Qdrant 走 qdrant-client。
> 型別註記慣例:函式簽章僅在必要時標註 `dict` / `list`,不引入 `typing` 匯入;不標註基本型別;dataclass 欄位照常。
> 設計取捨(相對設計規格書):(1) Loader 依來源、Parser 依格式拆分;(2) Chunker 先自寫 `CharacterChunker`,不引入 LangChain,日後可經同介面替換。

---

## File Structure

本計畫新增(沿用 P1 既有檔案):

```
pyproject.toml                          # 修改:新增 provider optional-dependencies
rag_adapter/
  loaders/
    __init__.py
    file_loader.py                      # FileLoader（讀檔/目錄）
    http_loaders.py                     # UrlLoader、TkmsLoader（皆走 HTTP）
  parsers/
    __init__.py
    html_parser.py                      # HtmlParser
    structured_parsers.py               # JsonParser、XmlParser
  chunkers/
    __init__.py
    character_chunker.py                # CharacterChunker
  embedders/
    __init__.py
    qwen_embedder.py                    # QwenEmbedder（API）
  vectorstores/
    __init__.py
    qdrant_store.py                     # QdrantVectorStore（client）
tests/
  test_html_parser.py
  test_structured_parsers.py
  test_file_loader.py
  test_http_loaders.py
  test_character_chunker.py
  test_qwen_embedder.py
  test_qdrant_store.py
  test_indexing_integration.py
```

責任邊界:每個 provider 一個聚焦檔案,只實作對應 `Protocol`;不含 pipeline 邏輯(pipeline 在 P1)。

---

## Task 1: provider 相依與套件目錄

**Files:**
- Modify: `pyproject.toml`
- Create: `rag_adapter/loaders/__init__.py`、`rag_adapter/parsers/__init__.py`、`rag_adapter/chunkers/__init__.py`、`rag_adapter/embedders/__init__.py`、`rag_adapter/vectorstores/__init__.py`

- [ ] **Step 1: 更新 pyproject.toml 的 optional-dependencies**

把 `[project.optional-dependencies]` 區塊整段替換為:
```toml
[project.optional-dependencies]
dev = ["pytest>=8.0", "beautifulsoup4>=4.12", "httpx>=0.27", "qdrant-client>=1.9"]
html = ["beautifulsoup4>=4.12"]
http = ["httpx>=0.27"]
qdrant = ["qdrant-client>=1.9"]
all = ["beautifulsoup4>=4.12", "httpx>=0.27", "qdrant-client>=1.9"]
```

- [ ] **Step 2: 建立空 package 檔**

以下五個檔案內容皆為空字串:
`rag_adapter/loaders/__init__.py`、`rag_adapter/parsers/__init__.py`、`rag_adapter/chunkers/__init__.py`、`rag_adapter/embedders/__init__.py`、`rag_adapter/vectorstores/__init__.py`

- [ ] **Step 3: 安裝相依並驗證**

Run: `pip install -e ".[dev]" && python -c "import bs4, httpx, qdrant_client; print('deps ok')"`
Expected: 印出 `deps ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml rag_adapter/loaders/__init__.py rag_adapter/parsers/__init__.py rag_adapter/chunkers/__init__.py rag_adapter/embedders/__init__.py rag_adapter/vectorstores/__init__.py
git commit -m "chore: add provider deps and package dirs for indexing"
```

---

## Task 2: HtmlParser

**Files:**
- Create: `rag_adapter/parsers/html_parser.py`
- Test: `tests/test_html_parser.py`

- [ ] **Step 1: 寫失敗測試**

`tests/test_html_parser.py`:
```python
from rag_adapter.models import Document, SourceRef
from rag_adapter.parsers.html_parser import HtmlParser


def test_html_parser_strips_tags_and_extracts_title():
    html = (
        "<html><head><title> Hi </title></head>"
        "<body><p>Hello <b>world</b></p><script>x()</script></body></html>"
    )
    doc = Document(id="d1", text=html, source_ref=SourceRef(loader="url", location="http://x"))
    out = HtmlParser().parse(doc)

    assert out.id == "d1"
    assert out.text == "Hi Hello world"
    assert out.metadata["title"] == "Hi"
    assert out.source_ref.location == "http://x"


def test_html_parser_without_title():
    doc = Document(id="d2", text="<p>just body</p>")
    out = HtmlParser().parse(doc)

    assert out.text == "just body"
    assert "title" not in out.metadata
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_html_parser.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'rag_adapter.parsers.html_parser'`

- [ ] **Step 3: 實作 html_parser.py**

`rag_adapter/parsers/html_parser.py`:
```python
from bs4 import BeautifulSoup

from rag_adapter.models import Document


class HtmlParser:
    """把 HTML 去標籤,抽出純文字與 <title>。供 url / tkms 等 HTML 來源使用。"""

    def parse(self, document):
        soup = BeautifulSoup(document.text, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())
        metadata = dict(document.metadata)
        if soup.title and soup.title.string:
            metadata["title"] = soup.title.string.strip()
        return Document(
            id=document.id,
            text=text,
            metadata=metadata,
            source_ref=document.source_ref,
        )
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_html_parser.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/parsers/html_parser.py tests/test_html_parser.py
git commit -m "feat: add html parser"
```

---

## Task 3: JsonParser 與 XmlParser

**Files:**
- Create: `rag_adapter/parsers/structured_parsers.py`
- Test: `tests/test_structured_parsers.py`

- [ ] **Step 1: 寫失敗測試**

`tests/test_structured_parsers.py`:
```python
from rag_adapter.models import Document
from rag_adapter.parsers.structured_parsers import JsonParser, XmlParser


def test_json_parser_collects_string_values_recursively():
    doc = Document(
        id="d1",
        text='{"title": "Hello", "meta": {"author": "amy"}, "tags": ["a", "b"], "n": 3}',
    )
    out = JsonParser().parse(doc)

    assert out.text == "Hello\namy\na\nb"
    assert out.id == "d1"


def test_xml_parser_collects_text_nodes():
    doc = Document(
        id="d2",
        text="<doc><title>Hello</title><body>world <b>here</b></body></doc>",
    )
    out = XmlParser().parse(doc)

    assert out.text == "Hello\nworld\nhere"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_structured_parsers.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'rag_adapter.parsers.structured_parsers'`

- [ ] **Step 3: 實作 structured_parsers.py**

`rag_adapter/parsers/structured_parsers.py`:
```python
import json
import xml.etree.ElementTree as ET

from rag_adapter.models import Document


class JsonParser:
    """遞迴取出 JSON 中所有字串值,以換行串接為文字。"""

    def parse(self, document):
        parts = []
        self._collect(json.loads(document.text), parts)
        return Document(
            id=document.id,
            text="\n".join(parts),
            metadata=dict(document.metadata),
            source_ref=document.source_ref,
        )

    def _collect(self, node, parts):
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                self._collect(value, parts)
        elif isinstance(node, list):
            for item in node:
                self._collect(item, parts)


class XmlParser:
    """取出 XML 所有文字節點,以換行串接。"""

    def parse(self, document):
        root = ET.fromstring(document.text)
        parts = [t.strip() for t in root.itertext() if t and t.strip()]
        return Document(
            id=document.id,
            text="\n".join(parts),
            metadata=dict(document.metadata),
            source_ref=document.source_ref,
        )
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_structured_parsers.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/parsers/structured_parsers.py tests/test_structured_parsers.py
git commit -m "feat: add json and xml parsers"
```

---

## Task 4: FileLoader

**Files:**
- Create: `rag_adapter/loaders/file_loader.py`
- Test: `tests/test_file_loader.py`

- [ ] **Step 1: 寫失敗測試**

`tests/test_file_loader.py`:
```python
from rag_adapter.loaders.file_loader import FileLoader


def test_file_loader_reads_single_file(tmp_path):
    f = tmp_path / "a.html"
    f.write_text("<p>hi</p>", encoding="utf-8")

    docs = FileLoader(loader_name="html").load(str(f))

    assert len(docs) == 1
    assert docs[0].text == "<p>hi</p>"
    assert docs[0].id == str(f)
    assert docs[0].source_ref.loader == "html"
    assert docs[0].source_ref.location == str(f)


def test_file_loader_reads_directory_recursively(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_text("A", encoding="utf-8")
    (tmp_path / "sub" / "b.txt").write_text("B", encoding="utf-8")

    docs = FileLoader().load(str(tmp_path))

    texts = sorted(d.text for d in docs)
    assert texts == ["A", "B"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_file_loader.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'rag_adapter.loaders.file_loader'`

- [ ] **Step 3: 實作 file_loader.py**

`rag_adapter/loaders/file_loader.py`:
```python
from pathlib import Path

from rag_adapter.models import Document, SourceRef


class FileLoader:
    """從檔案路徑或目錄讀取原始內容(不解析)。目錄則遞迴讀取所有檔案。"""

    def __init__(self, loader_name="file"):
        self._loader_name = loader_name

    def load(self, location):
        documents = []
        for path in self._resolve(location):
            text = path.read_text(encoding="utf-8")
            ref = SourceRef(loader=self._loader_name, location=str(path))
            documents.append(Document(id=str(path), text=text, source_ref=ref))
        return documents

    def _resolve(self, location):
        path = Path(location)
        if path.is_dir():
            return sorted(p for p in path.rglob("*") if p.is_file())
        return [path]
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_file_loader.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/loaders/file_loader.py tests/test_file_loader.py
git commit -m "feat: add file loader"
```

---

## Task 5: UrlLoader 與 TkmsLoader（HTTP)

**Files:**
- Create: `rag_adapter/loaders/http_loaders.py`
- Test: `tests/test_http_loaders.py`

說明:兩者皆以注入的 HTTP client(預設 `httpx.Client`)抓取原始 HTML;TKMS 為公司內部 wiki,依 page id 組出 URL。測試注入假 client,不需網路。

- [ ] **Step 1: 寫失敗測試**

`tests/test_http_loaders.py`:
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

    def get(self, url):
        self.requested.append(url)
        return FakeResponse(self._mapping[url])


def test_url_loader_fetches_multiple_urls():
    client = FakeHttpClient({
        "http://a": "<p>A</p>",
        "http://b": "<p>B</p>",
    })
    docs = UrlLoader(client=client).load(["http://a", "http://b"])

    assert [d.text for d in docs] == ["<p>A</p>", "<p>B</p>"]
    assert docs[0].id == "http://a"
    assert docs[0].source_ref.loader == "url"


def test_tkms_loader_builds_page_urls():
    client = FakeHttpClient({"https://wiki/pages/42": "<p>wiki</p>"})
    docs = TkmsLoader(base_url="https://wiki/pages/", client=client).load("42")

    assert client.requested == ["https://wiki/pages/42"]
    assert docs[0].text == "<p>wiki</p>"
    assert docs[0].source_ref.loader == "tkms"
    assert docs[0].source_ref.location == "https://wiki/pages/42"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_http_loaders.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'rag_adapter.loaders.http_loaders'`

- [ ] **Step 3: 實作 http_loaders.py**

`rag_adapter/loaders/http_loaders.py`:
```python
import httpx

from rag_adapter.models import Document, SourceRef


def _as_list(value):
    return [value] if isinstance(value, str) else list(value)


class UrlLoader:
    """以 HTTP GET 抓取一或多個 URL 的原始內容(通常為 HTML),不解析。"""

    def __init__(self, client=None, loader_name="url"):
        self._client = client or httpx.Client(timeout=30)
        self._loader_name = loader_name

    def load(self, location):
        documents = []
        for url in _as_list(location):
            response = self._client.get(url)
            response.raise_for_status()
            ref = SourceRef(loader=self._loader_name, location=url)
            documents.append(Document(id=url, text=response.text, source_ref=ref))
        return documents


class TkmsLoader:
    """公司內部 wiki(TKMS)。目前以 HTML 處理:依 page id 組出 URL 抓取。"""

    def __init__(self, base_url, client=None):
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=30)

    def load(self, location):
        documents = []
        for page_id in _as_list(location):
            url = f"{self._base_url}/{page_id}"
            response = self._client.get(url)
            response.raise_for_status()
            ref = SourceRef(loader="tkms", location=url)
            documents.append(Document(id=url, text=response.text, source_ref=ref))
        return documents
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_http_loaders.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/loaders/http_loaders.py tests/test_http_loaders.py
git commit -m "feat: add url and tkms http loaders"
```

---

## Task 6: CharacterChunker

**Files:**
- Create: `rag_adapter/chunkers/character_chunker.py`
- Test: `tests/test_character_chunker.py`

- [ ] **Step 1: 寫失敗測試**

`tests/test_character_chunker.py`:
```python
import pytest

from rag_adapter.models import Document, SourceRef
from rag_adapter.chunkers.character_chunker import CharacterChunker


def test_character_chunker_splits_with_overlap():
    doc = Document(
        id="d1",
        text="abcdefghij",
        source_ref=SourceRef(loader="file", location="/p"),
    )
    chunks = CharacterChunker(chunk_size=4, chunk_overlap=1).chunk(doc)

    assert [c.text for c in chunks] == ["abcd", "defg", "ghij"]
    assert chunks[0].id == "d1#0"
    assert chunks[1].id == "d1#1"
    assert chunks[1].document_id == "d1"
    assert chunks[1].position == {"index": 1, "start": 3, "end": 7}
    assert chunks[0].source_ref.location == "/p"


def test_character_chunker_short_text_single_chunk():
    doc = Document(id="d2", text="hi")
    chunks = CharacterChunker(chunk_size=100, chunk_overlap=10).chunk(doc)

    assert len(chunks) == 1
    assert chunks[0].text == "hi"


def test_character_chunker_rejects_bad_overlap():
    with pytest.raises(ValueError):
        CharacterChunker(chunk_size=10, chunk_overlap=10)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_character_chunker.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'rag_adapter.chunkers.character_chunker'`

- [ ] **Step 3: 實作 character_chunker.py**

`rag_adapter/chunkers/character_chunker.py`:
```python
from rag_adapter.models import Chunk


class CharacterChunker:
    """以字元數切分的重疊滑動視窗 chunker。

    日後可在同一 Chunker 介面下替換為 recursive / token-based 版本。
    """

    def __init__(self, chunk_size=800, chunk_overlap=100):
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def chunk(self, document):
        text = document.text
        step = self._chunk_size - self._chunk_overlap
        chunks = []
        index = 0
        start = 0
        while start < len(text) or index == 0:
            end = min(start + self._chunk_size, len(text))
            chunks.append(
                Chunk(
                    id=f"{document.id}#{index}",
                    document_id=document.id,
                    text=text[start:end],
                    metadata=dict(document.metadata),
                    source_ref=document.source_ref,
                    position={"index": index, "start": start, "end": end},
                )
            )
            index += 1
            if end >= len(text):
                break
            start += step
        return chunks
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_character_chunker.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/chunkers/character_chunker.py tests/test_character_chunker.py
git commit -m "feat: add character chunker with overlap"
```

---

## Task 7: QwenEmbedder（OpenAI 相容 API)

**Files:**
- Create: `rag_adapter/embedders/qwen_embedder.py`
- Test: `tests/test_qwen_embedder.py`

說明:呼叫 OpenAI 相容的 `POST {base_url}/embeddings`,payload `{"model", "input": [...]}`,回傳 `data[i].embedding`。以 `batch_size` 分批。測試注入假 client。

- [ ] **Step 1: 寫失敗測試**

`tests/test_qwen_embedder.py`:
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

    def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        vectors = self._batches.pop(0)
        return FakeResponse({"data": [{"embedding": v} for v in vectors]})


def test_embed_fills_embeddings_and_batches():
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

    out = embedder.embed(chunks)

    assert [c.embedding for c in out] == [[1.0], [2.0], [3.0]]
    assert len(client.calls) == 2
    assert client.calls[0]["url"] == "https://api/v1/embeddings"
    assert client.calls[0]["headers"]["Authorization"] == "Bearer k"
    assert client.calls[0]["json"] == {"model": "text-embedding-v3", "input": ["a", "b"]}


def test_embed_query_returns_single_vector():
    client = FakeHttpClient(batches=[[[9.0]]])
    embedder = QwenEmbedder(
        base_url="https://api/v1",
        api_key="k",
        model="m",
        client=client,
    )

    assert embedder.embed_query("hello") == [9.0]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_qwen_embedder.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'rag_adapter.embedders.qwen_embedder'`

- [ ] **Step 3: 實作 qwen_embedder.py**

`rag_adapter/embedders/qwen_embedder.py`:
```python
import httpx


class QwenEmbedder:
    """以 OpenAI 相容的 /embeddings API 取得向量(Qwen 模型)。"""

    def __init__(self, base_url, api_key, model, client=None, batch_size=16):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.Client(timeout=60)
        self._batch_size = batch_size

    def embed(self, chunks):
        vectors = self._embed_texts([c.text for c in chunks])
        for chunk, vector in zip(chunks, vectors):
            chunk.embedding = vector
        return chunks

    def embed_query(self, text):
        return self._embed_texts([text])[0]

    def _embed_texts(self, texts):
        vectors = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start:start + self._batch_size]
            response = self._client.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "input": batch},
            )
            response.raise_for_status()
            vectors.extend(item["embedding"] for item in response.json()["data"])
        return vectors
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_qwen_embedder.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/embedders/qwen_embedder.py tests/test_qwen_embedder.py
git commit -m "feat: add qwen api embedder"
```

---

## Task 8: QdrantVectorStore（client)

**Files:**
- Create: `rag_adapter/vectorstores/qdrant_store.py`
- Test: `tests/test_qdrant_store.py`

說明:`chunk.id` 為字串,Qdrant point id 需為 uint/UUID,故以 `uuid5(NAMESPACE_URL, chunk.id)` 映成 point id,原始欄位存入 payload;search 時由 payload 還原 `Chunk`。client 由建構式注入(測試用假 client)。

- [ ] **Step 1: 寫失敗測試**

`tests/test_qdrant_store.py`:
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

    def upsert(self, collection_name, points):
        self.upserted = {"collection": collection_name, "points": points}

    def delete(self, collection_name, points_selector):
        self.deleted = {"collection": collection_name, "selector": points_selector}

    def search(self, collection_name, query_vector, limit):
        self.search_args = {
            "collection": collection_name,
            "query_vector": query_vector,
            "limit": limit,
        }
        return self._hits


def _expected_point_id(chunk_id):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def test_upsert_maps_chunk_to_point_with_payload():
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

    store.upsert([chunk])

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


def test_delete_maps_ids():
    client = FakeQdrantClient()
    store = QdrantVectorStore(client=client, collection="docs")

    store.delete(["c1"])

    assert client.deleted["selector"] == [_expected_point_id("c1")]


def test_search_reconstructs_retrieved_chunks():
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

    results = store.search([0.1, 0.2], top_k=3)

    assert client.search_args["limit"] == 3
    assert results[0].score == 0.87
    assert results[0].chunk.id == "c1"
    assert results[0].chunk.text == "hello"
    assert results[0].chunk.source_ref.loader == "url"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_qdrant_store.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'rag_adapter.vectorstores.qdrant_store'`

- [ ] **Step 3: 實作 qdrant_store.py**

`rag_adapter/vectorstores/qdrant_store.py`:
```python
import uuid

from qdrant_client import models as qmodels

from rag_adapter.models import Chunk, RetrievedChunk, SourceRef


def _point_id(chunk_id):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


class QdrantVectorStore:
    """以 qdrant-client 儲存 / 查詢向量。

    chunk.id 以 uuid5 映成 point id,原始欄位存於 payload,search 時還原為 Chunk。
    collection 的建立與向量維度設定由呼叫端先行處理。
    """

    def __init__(self, client, collection):
        self._client = client
        self._collection = collection

    def upsert(self, chunks):
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
        self._client.upsert(collection_name=self._collection, points=points)

    def delete(self, chunk_ids):
        self._client.delete(
            collection_name=self._collection,
            points_selector=[_point_id(cid) for cid in chunk_ids],
        )

    def search(self, embedding, top_k):
        hits = self._client.search(
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

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_qdrant_store.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/vectorstores/qdrant_store.py tests/test_qdrant_store.py
git commit -m "feat: add qdrant vector store"
```

---

## Task 9: Indexing 整合測試（真實 loader/parser/chunker 組裝)

**Files:**
- Test: `tests/test_indexing_integration.py`

說明:用**真實**的 FileLoader + HtmlParser + CharacterChunker,搭配 P1 的 `IndexingPipeline`,以及 P1 testing mocks 的 `EchoEmbedder` + `InMemoryVectorStore`(避免外部服務),證明各層能端到端組裝並索引。

- [ ] **Step 1: 寫測試**

`tests/test_indexing_integration.py`:
```python
from rag_adapter.pipeline.indexing import IndexingPipeline
from rag_adapter.loaders.file_loader import FileLoader
from rag_adapter.parsers.html_parser import HtmlParser
from rag_adapter.chunkers.character_chunker import CharacterChunker
from rag_adapter.testing.mocks import EchoEmbedder, InMemoryVectorStore


def test_real_indexing_components_compose(tmp_path):
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

    count = pipeline.index(str(page))

    assert count >= 2  # 50 個 word 會被切成多個 chunk
    results = store.search([80.0], top_k=1)
    assert results[0].chunk.document_id == str(page)
    assert results[0].chunk.source_ref.loader == "html"
    assert "title" in results[0].chunk.metadata
```

- [ ] **Step 2: 跑測試確認通過**

Run: `pytest tests/test_indexing_integration.py -v`
Expected: PASS（1 passed）

> 註:本測試無「先失敗」步驟,因為它只組裝既有元件、不新增產品程式碼。

- [ ] **Step 3: 跑全部測試**

Run: `pytest -q`
Expected: PASS（P1 的 12 + P2 新增,全部 passed）

- [ ] **Step 4: Commit**

```bash
git add tests/test_indexing_integration.py
git commit -m "test: add indexing pipeline integration with real components"
```

---

## Self-Review

**Spec coverage(對照設計規格書 Indexing 區塊):**
- Loader(html/tkms/json/xml)→ FileLoader/UrlLoader/TkmsLoader(來源)+ Html/Json/Xml Parser(格式)共同涵蓋 ✓
- Parser:Html(Task 2)、Json/Xml(Task 3)✓
- Chunker:CharacterChunker(Task 6)✓(token-based 為 v1 之後)
- Embedder(Qwen):API 實作(Task 7)✓
- VectorStore(Qdrant):含 upsert/delete/search(Task 8)✓
- 與 IndexingPipeline 組裝:整合測試(Task 9)✓
- 可替換:全部實作只依賴 P1 `Protocol`,client/相依皆注入 ✓

**Placeholder scan:** 無 TBD/TODO;每個 code step 皆含完整程式碼。

**Type consistency:** Parser 回 `Document`;Loader 回 `list[Document]`;Chunker 回 `list[Chunk]`;Embedder 就地填 `embedding` 並回傳同批;VectorStore.search 回 `list[RetrievedChunk]`;與 P1 介面約定一致。`source_ref` 序列化/還原鍵為 `loader/location/position`,upsert 與 search 對稱。

---

## 後續計畫(另開 docs)
- **P3 Query**:cosine/BM25 Retriever、RRF Fusion、Qwen Reranker、ContextBuilder
- **P4 Generation**:PromptBuilder、Qwen Generator(generate/stream)
- **P5 Obs + Eval**:Langfuse trace、Retrieval 指標
```

