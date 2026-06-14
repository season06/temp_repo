# RAG Adapter Tech Stack

## 1. 基本前提

本 RAG Adapter 以地端部署為主，模型使用開源模型，不預設依賴雲端 LLM、雲端 embedding provider 或 managed reranker。

核心設計原則：

- 模型服務、向量庫、觀測工具都透過 adapter interface 接入。
- 核心 pipeline 不直接綁定 LangChain、LangGraph 或特定模型 serving runtime。
- LangChain / LangGraph 可作為 optional integration，用於需要 workflow、agent 或 tool orchestration 的情境。
- 所有 request 都要能產生 trace，並透過既有自製 SDK 寫入 Langfuse。

## 2. 語言與 Runtime

建議版本：

- Python 3.12+

基礎套件：

- `pydantic`：資料模型與 config schema。
- `pydantic-settings`：環境變數與設定檔載入。
- `fastapi`：API service。
- `uvicorn`：ASGI server。
- `httpx`：呼叫地端模型服務。
- `tenacity`：retry。
- `pyyaml`：YAML config。
- `orjson`：高效 JSON serialization。

工程工具：

- `uv`：package manager。
- `ruff`：lint 與 format。
- `pytest`：測試。
- `pytest-asyncio`：async 測試。
- `mypy` 或 `pyright`：型別檢查。

## 3. 模型

### 3.1 Embedding Model

指定模型：
- Qwen embedding model

Adapter 要求：

- 支援 batch embedding。
- 支援 async request。
- 支援 retry 與 timeout。
- 支援 embedding cache。
- 寫入 vector store 時必須記錄：
  - `embedding_provider`
  - `embedding_model`
  - `embedding_dimension`
  - `embedding_version`

建議 interface：

```python
from typing import Protocol


class Embedder(Protocol):
    model_name: str
    dimension: int

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...

    async def embed_query(self, query: str) -> list[float]:
        ...
```

注意事項：

- 若未來更換 embedding model 或 dimension，應建立新 collection 或新 index namespace，不要直接混用。
- Chunk metadata 應記錄 embedding model 版本，方便重建索引與 debug。

### 3.2 Reranker Model

指定模型：

- Qwen reranker model。

Adapter 要求：

- 輸入 query 與候選 chunks。
- 輸出 rerank score。
- 保留原始 retrieval score。
- 支援 batch reranking。
- 支援 top-n 截斷。

建議 interface：

```python
from dataclasses import dataclass
from typing import Protocol


@dataclass
class RerankInput:
    query: str
    chunk_id: str
    text: str
    retrieval_score: float


@dataclass
class RerankOutput:
    chunk_id: str
    retrieval_score: float
    rerank_score: float


class Reranker(Protocol):
    model_name: str

    async def rerank(self, query: str, inputs: list[RerankInput]) -> list[RerankOutput]:
        ...
```

建議預設策略：

- Retrieval top-k：20。
- Rerank top-n：8。
- Context builder 最終選用：依 token budget 決定。

## 4. Framework

指定方向：

- LangChain：optional。
- LangGraph：optional。

使用原則：

- 核心 RAG Adapter 不依賴 LangChain / LangGraph 的資料模型。
- 若使用 LangChain，放在 integration layer，不要讓業務端直接依賴 LangChain object。
- 若使用 LangGraph，建議只用於多步流程，例如 query rewrite、multi-hop retrieval、approval workflow 或 agentic RAG。

建議分層：

```text
Application
  -> RAG Adapter public API
  -> Core interfaces
  -> Provider adapters
  -> Optional LangChain / LangGraph integrations
```

可選 integration：

- LangChain document loader bridge。
- LangChain retriever bridge。
- LangChain tool wrapper。
- LangGraph node wrapper。

## 5. Vector Store

第一優先建議：

- Qdrant。

備選：

- PostgreSQL + pgvector。

選擇理由：

- Qdrant 對 metadata filter、collection 管理、payload schema 與 local deployment 較直覺。
- pgvector 適合已經有 PostgreSQL 基礎設施，並希望減少額外服務的團隊。

必要 schema：

- distance metric：cosine。
- payload metadata：
  - `tenant_id`
  - `document_id`
  - `chunk_id`
  - `source_uri`
  - `title`
  - `section_path`
  - `page_number`
  - `acl`
  - `created_at`
  - `updated_at`
  - `embedding_model`
  - `embedding_dimension`

## 6. Document Parsing

第一版建議：

- Markdown：自製 heading-aware parser 或 `markdown-it-py`。
- TXT：內建 reader。
- HTML：`beautifulsoup4`。
- PDF：`pymupdf` 或 `pypdf`。

後續可加入：

- `docling`：較完整的文件解析 pipeline。
- `unstructured`：多格式解析。
- OCR：Tesseract 或既有內部 OCR 服務。

## 7. Chunking

建議自製 chunker，原因是 metadata 與 citation 是核心能力，不應完全交給 framework 控制。

第一版支援：

- Recursive text chunker。
- Token-aware chunker。
- Markdown heading-aware chunker。

建議預設：

- `chunk_size`: 800 到 1200 tokens。
- `chunk_overlap`: 100 到 150 tokens。
- `merge_small_chunks`: true。
- `preserve_headings`: true。

實際參數應透過 evaluation dataset 調整。

## 8. Observability

指定工具：

- Langfuse。
- 已有自製 SDK。

整合方式：

- RAG Adapter 只依賴內部 observability interface。
- Langfuse 寫入邏輯包在 adapter 中。
- 若 Langfuse 或 SDK 暫時不可用，pipeline 不應整體失敗，應降級為 local JSON log。

必要 trace 欄位：

- `trace_id`
- `user_id`
- `tenant_id`
- `query`
- `normalized_query`
- `filters`
- `retrieval_top_k`
- `retrieved_chunks`
- `retrieval_scores`
- `rerank_model`
- `rerank_scores`
- `selected_chunks`
- `context_token_count`
- `citations`
- `latency_ms`
- `error`

建議 interface：

```python
from typing import Any, Protocol


class RagTracer(Protocol):
    async def start_trace(self, name: str, metadata: dict[str, Any]) -> str:
        ...

    async def add_event(
        self,
        trace_id: str,
        name: str,
        metadata: dict[str, Any],
    ) -> None:
        ...

    async def end_trace(
        self,
        trace_id: str,
        output: dict[str, Any],
        error: str | None = None,
    ) -> None:
        ...
```

## 9. Evaluation

第一版建議：

- `pytest`：pipeline 單元測試與整合測試。
- 自製 retrieval eval：recall@k、precision@k、MRR、empty retrieval rate。
- Langfuse dataset 或內部資料集：記錄 production query 與人工標註結果。

後續可加入：

- `ragas`。
- `deepeval`。
- LLM-as-judge，但需使用地端 judge model 或明確隔離資料。

## 10. 建議第一版組合

```text
Language: Python 3.12+
API: FastAPI
Config: Pydantic + YAML
Embedding: Qwen embedding, 4096 dimensions
Reranker: Qwen reranker
Vector DB: Qdrant, with in-memory store for tests
Parsing: pymupdf/pypdf, beautifulsoup4, markdown-it-py
Chunking: custom recursive + token-aware chunker
Framework: LangChain / LangGraph optional integrations
Observability: Langfuse via existing internal SDK
Testing: pytest + pytest-asyncio + custom retrieval eval
Packaging: uv + ruff + mypy/pyright
```

## 11. 實作優先順序

1. 定義 Python core types 與 config schema。
2. 建立 local file ingestion。
3. 實作 chunker。
4. 實作 Qwen embedder adapter。
5. 建立 Qdrant vector store adapter，dimension 固定為 4096。
6. 實作 dense retriever。
7. 實作 Qwen reranker adapter。
8. 實作 context builder 與 citations。
9. 串接 Langfuse internal SDK。
10. 補上 LangChain / LangGraph optional integration。
11. 建立 retrieval eval。

## 12. 關鍵決策

- Qwen embedding dimension 4096 是索引 schema 的核心約束，必須進入 config validation。
- LangChain / LangGraph 只能作為 optional integration，不能成為核心資料模型。
- Langfuse integration 必須非阻塞或可降級，避免觀測系統影響主要查詢流程。
- Retrieval 與 reranking 分數都要保留，方便評估與 debug。
- 模型版本、embedding dimension、chunking config 都要寫入 metadata，方便重建索引。
