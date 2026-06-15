# RAG Adapter SDK

一套可供多數專案使用的 **RAG Adapter SDK**: 把資料接入、解析、切分、Embedding、索引、檢索、重排、上下文組裝抽象成**可替換模組**,讓不同團隊依需求替換模型、向量庫、資料來源與檢索策略。

## Current Supports

| Component | Support Type |
|-----------|----------|
| Loader | `file`、`url`、`tkms`(內部 wiki,以 HTML 處理) |
| Parser | `html`、`json`、`xml` |
| Chunker | `character` (重疊滑動視窗) |
| Embedder | `qwen` (OpenAI 相容 API) |
| Vector Store | `qdrant` |

> Query 側(Retriever / Reranker / ContextBuilder / Generator)的介面與測試替身已就緒,真實 provider 規劃於後續階段(見 `docs/superpowers/plans/`)。

---

# (for User)

RAG Adapter SDK 是一個 Python library
撰寫少量程式碼即可組裝一條 RAG pipeline, 以 config 方式快速替換 provider (包含 Data Source / Model / VectorDB / Retrieval Strategy)

## Installation

```bash
pip install -e ".[all]"     # 含 html / http / qdrant 等 provider 相依
# 或只裝需要的:pip install -e ".[html,qdrant]"
```

## Quick-Start: 建立 indexing pipeline

可直接執行的範例(使用 in-memory 假 embedder / store,無需外部服務):

```bash
python examples/indexing_quickstart.py
# 輸出:indexed 6 chunks from handbook.html
```

程式重點(節錄自 `examples/indexing_quickstart.py`):

```python
import asyncio
from rag_adapter.pipeline.indexing import IndexingPipeline
from rag_adapter.loaders.file_loader import FileLoader
from rag_adapter.parsers.html_parser import HtmlParser
from rag_adapter.chunkers.character_chunker import CharacterChunker
from rag_adapter.testing.mocks import EchoEmbedder, InMemoryVectorStore

pipeline = IndexingPipeline(
    loader=FileLoader(loader_name="html"),
    parser=HtmlParser(),
    chunker=CharacterChunker(chunk_size=200, chunk_overlap=20),
    embedder=EchoEmbedder(),             # 正式環境改用 QwenEmbedder
    vector_store=InMemoryVectorStore(),  # 正式環境改用 QdrantVectorStore
)

count = asyncio.run(pipeline.index("./your_docs"))
```

要換成正式 provider,只需替換對應參數,**pipeline 結構不變**——這就是「可替換」的核心。

## Config-Driven (正式環境)

不想在程式裡手動組裝,可用 YAML 配置(secrets 以 `${ENV:VAR}` 從環境變數插值):

```yaml
# examples/rag.yaml
indexing:
  loader: { type: file, loader_name: html }
  parser: { type: html }
  chunker: { type: character, chunk_size: 800, chunk_overlap: 100 }
  embedder:
    type: qwen
    base_url: ${ENV:QWEN_BASE_URL}
    api_key: ${ENV:QWEN_API_KEY}
    model: qwen-embedding
  vector_store: { type: qdrant, url: http://localhost:6333, collection: documents }
```

```python
from rag_adapter.config import load_config
from rag_adapter.factory import build_indexing_pipeline

config = load_config("examples/rag.yaml")
pipeline = build_indexing_pipeline(config)   # 需 Qdrant server + Qwen API
```

---

# (for Developer)

## Design Pattern ↔ Code Base

設計依循 5 個 pattern(詳見設計規格書 §7)。下表是「pattern → 實際落在哪些檔案」:

| Pattern | Description | Source Code |
|---------|-------------|-------------|
| **Interface-Driven** | 所有模組透過 `Protocol` 定義介面,實作可替換 | `rag_adapter/interfaces.py`(12 個 `@runtime_checkable` Protocol) |
| **Type-First** | 以 dataclass 定義資料結構 | 資料模型 `rag_adapter/models.py`;config schema `rag_adapter/config.py`(frozen dataclass + `__post_init__` 驗證) |
| **Async-First(僅 I/O 層)** | 有 I/O 的層用 `async/await`;純 CPU 層維持同步 | async:`loaders/`、`embedders/`、`vectorstores/`、Retriever/Reranker/Generator 介面。sync:`parsers/`、`chunkers/`、Fusion/ContextBuilder/PromptBuilder |
| **Config-Driven** | YAML 配置 → 工廠組裝 pipeline | `rag_adapter/config.py`(只做 config:載入/驗證/插值)、`rag_adapter/factory.py`(根據 config 建 pipeline) |
| **Pipeline** | 以 Pipeline 串接元件 | `rag_adapter/pipeline/indexing.py`、`rag_adapter/pipeline/query.py` |

## 架構分層

```
資料流(Indexing):  Loader → Parser → Chunker → Embedder → VectorStore
資料流(Query):     Retriever(多路) → Fusion → Reranker → ContextBuilder → (PromptBuilder → Generator)
貫穿全程的契約:     rag_adapter/models.py 的 Document / Chunk / RetrievedChunk / Citation / Answer
組裝:              config.py(YAML→RagConfig) → factory.py → pipeline/
```

**關鍵職責邊界:**
- `config.py` 只負責配置(載入 / 驗證 / 持有 typed `RagConfig`),**不 import 任何 provider**。
- `factory.py` 負責「config → 建立 provider → 組裝 pipeline」,是 config 與實作之間的唯一橋樑。
- `pipeline/*` 只負責「依序呼叫注入的各層」,不含任何 provider 邏輯。
- `interfaces.py` 只定義 Protocol,無實作。

## Async 邊界(務必遵守)

Async **只套 I/O 層**。pipeline 在 I/O 步驟 `await`,CPU 步驟直接呼叫:

| async(`async def` + await) | sync(一般 `def`) |
|---|---|
| Loader.load、Embedder.embed/embed_query、VectorStore.upsert/delete/search、Retriever.retrieve、Reranker.rerank、Generator.generate | Parser.parse、Chunker.chunk、Fusion.fuse、ContextBuilder.build、PromptBuilder.build_prompt、QueryTransform.transform |

`Generator.stream` 為 async generator;`FileLoader` 以 `asyncio.to_thread` 包磁碟讀取避免阻塞事件迴圈。

## How to Create a Provider

以新增一個 Embedder 為例:

1. 在 `rag_adapter/embedders/` 新增檔案,實作 `Embedder` Protocol(`async def embed`、`async def embed_query`)——**不需繼承任何基底類別**,符合介面即可(duck typing)。
2. 若要支援 config 驅動:在 `rag_adapter/config.py` 的 `EmbedderConfig` 加上需要的欄位,並在 `rag_adapter/factory.py` 的 `_build_embedder` 加上對應 `type` 分支。
3. 在 `tests/` 加上單元測試(外部 I/O 用注入的假 client,見既有 `test_qwen_embedder.py`)。

其餘層(Loader / Parser / Chunker / VectorStore …)做法相同:實作對應 Protocol → (選用)接 config + factory → 加測試。

## Typing

- **一般程式**:函式簽章只在參數 / 回傳為 `dict` / `list` 時標註;不引入 `typing`、不標基本型別。
- **例外:`config.py`**:config schema 採滿型別 frozen dataclass(`int` / `str | None` / `__post_init__` 驗證),作為對外配置契約。

## Testing

```bash
pip install -e ".[dev]"
pytest -q          # 目前 35 passed
```

- 採 `pytest-asyncio`,`pyproject.toml` 設 `asyncio_mode = "auto"`,故 `async def test_...` 不需裝飾子。
- I/O 層測試用注入的**假 client**(fake httpx / fake qdrant client),不碰網路或真實服務。
- `rag_adapter/testing/mocks.py` 提供各層的 in-memory 測試替身,可用來組裝端到端 pipeline 測試(見 `test_indexing_integration.py`)。

## Folder Structure

```
rag_adapter/
  interfaces.py        # 全層 Protocol(Pattern 1)
  models.py            # 資料模型 dataclass(Pattern 2)
  config.py            # YAML → typed RagConfig(Pattern 2 + 4,只做 config)
  factory.py           # config → 組裝 pipeline(Pattern 4)
  pipeline/            # IndexingPipeline / QueryPipeline(Pattern 5)
  loaders/ parsers/ chunkers/ embedders/ vectorstores/   # provider 實作(Pattern 3)
  testing/mocks.py     # 測試替身
examples/              # quick-start 範例 + rag.yaml
tests/                 # 對應各層的測試
docs/superpowers/      # specs(設計)與 plans(分階段實作計畫)
```
