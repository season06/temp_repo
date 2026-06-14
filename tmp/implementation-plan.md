# RAG Adapter 實作計畫

## 1. 目標

設計並實作一個可供多數專案使用的 RAG Adapter。它應該把資料接入、解析、切分、Embedding、索引、檢索、重排、上下文組裝、引用、觀測與治理抽象成可替換模組，讓不同團隊能依需求替換模型、向量庫、資料來源與檢索策略。

核心目標：

- 開箱即用：提供一組預設 pipeline，能快速支援常見文件與向量庫。
- 可替換：各層模組以穩定 interface 串接，不綁死特定 provider。
- 可追溯：每次回答都能回溯來源文件、chunk、分數與組裝後 context。
- 可治理：支援多租戶、權限過濾、刪除同步、資料版本與 audit log。
- 可評估：內建 retrieval 與 answer quality 的離線評估流程。

## 2. 非目標

第一版不追求支援所有資料來源與所有向量庫，而是先建立穩定架構與最小可用能力。

暫不處理：

- 完整 UI 管理後台。
- 複雜 agent workflow。
- 自動知識圖譜建置。
- 所有檔案格式的完美解析。
- 完全自動的 prompt injection 判定。

## 3. 使用情境

主要使用者：

- 應用工程師：需要在產品內快速加入文件問答。
- 平台工程師：需要替多團隊提供統一 RAG 基礎設施。
- 資料工程師：需要建立可同步、可重建、可觀測的知識索引。
- 評估工程師：需要比較 chunking、embedding、retrieval、reranking 策略。

典型流程：

1. 設定資料來源。
2. 載入與解析文件。
3. 切分 chunk 並建立 embedding。
4. 寫入 vector store。
5. 使用 query 觸發檢索。
6. 套用 metadata filter 與權限條件。
7. 重排結果。
8. 組裝 context。
9. 呼叫 LLM 產生答案。
10. 回傳答案、引用與 trace。

## 4. 系統架構

建議採用 pipeline + plugin adapter 架構。

```text
Sources
  -> Loader
  -> Parser
  -> Chunker
  -> Embedder
  -> Vector Store
  -> Retriever
  -> Reranker
  -> Context Builder
  -> Generator
  -> Answer + Citations + Trace
```

各模組透過 interface 溝通，避免業務邏輯依賴特定實作。

## 5. 核心模組

### 5.1 Source Loader

第一版支援：

- Markdown
- TXT
- HTML
- PDF
- Local directory

後續支援：

- Google Drive
- Notion
- Confluence
- SharePoint
- S3 / GCS / Azure Blob
- Database connector
- Custom API connector

必要能力：

- 增量同步。
- 刪除同步。
- 檔案 hash。
- 來源 metadata。
- 文件版本。
- 錯誤重試。

### 5.2 Parser

必要能力：

- 抽取正文。
- 保留標題層級。
- 保留頁碼、段落、來源 URL。
- 基礎表格轉文字。
- 移除重複空白與常見噪音。

第一版可用簡化策略，後續再強化 OCR、表格結構化與圖片描述。

### 5.3 Chunker

第一版支援：

- Recursive text splitter。
- Token-based splitter。
- Markdown heading-aware splitter。

必要 metadata：

- `document_id`
- `chunk_id`
- `source_uri`
- `title`
- `section_path`
- `page_number`
- `start_offset`
- `end_offset`
- `created_at`
- `updated_at`
- `tenant_id`
- `acl`

設定項：

- `chunk_size`
- `chunk_overlap`
- `max_chunk_tokens`
- `preserve_headings`
- `merge_small_chunks`

### 5.4 Embedder

第一版支援：

- OpenAI embedding provider。
- 本地 mock embedder，供測試使用。

後續支援：

- Cohere
- Voyage
- Bedrock
- Azure OpenAI
- Local embedding model

必要能力：

- Batch embedding。
- Retry。
- Rate limit。
- Cache。
- 記錄 model name、dimension、provider、version。

### 5.5 Vector Store

第一版建議支援：

- pgvector 或 Qdrant。
- In-memory store，供單元測試與本地 demo 使用。

必要 interface：

- `upsert`
- `delete`
- `query`
- `hybridQuery`
- `getByIds`
- `healthCheck`

必要能力：

- Metadata filter。
- Tenant namespace。
- Score threshold。
- Index schema validation。
- Reindex support。

### 5.6 Retriever

第一版支援：

- Dense vector search。
- Metadata filter。
- Top-k retrieval。
- Score threshold。

後續支援：

- BM25。
- Hybrid search。
- Query rewriting。
- Multi-query retrieval。
- Parent-child retrieval。
- Time-aware retrieval。
- ACL-aware retrieval。

### 5.7 Reranker

第一版支援：

- No-op reranker。
- Score-based reranker。

後續支援：

- Cross-encoder reranker。
- Provider reranker。
- LLM reranker。

必要輸出：

- 原始 retrieval score。
- rerank score。
- rerank reason，可選。

### 5.8 Context Builder

必要能力：

- 依 token budget 組裝 context。
- 去除重複 chunk。
- 合併同文件相鄰 chunk。
- 保留 citation marker。
- 限制每份文件最大佔比。
- 支援不同回答模式。

第一版回答模式：

- `concise`
- `detailed`
- `strict_citation`

### 5.9 Generator

第一版可設計為可插拔，不強制綁定 LLM provider。

必要能力：

- 接收 query、context、system instruction。
- 回傳 answer、citations、usage。
- 支援 streaming，可後續實作。

### 5.10 Trace 與 Observability

每次 request 應輸出 trace：

- query。
- normalized query。
- filters。
- retrieval candidates。
- retrieval scores。
- rerank scores。
- selected chunks。
- context token count。
- provider latency。
- cost estimate。
- final citations。

Metrics：

- request count。
- error count。
- retrieval latency。
- rerank latency。
- generation latency。
- empty result rate。
- average context tokens。
- citation coverage。

## 6. 建議 Interface

以下以 Python 表示概念，實作時建議使用 `dataclass` 或 Pydantic model 定義資料結構，並以 `Protocol` 或抽象基底類別定義可替換模組。

```python
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class RawDocument:
    id: str
    source_uri: str
    content: bytes | str
    metadata: dict[str, Any] = field(default_factory=dict)
    mime_type: str | None = None


@dataclass
class ParsedSection:
    title: str | None
    text: str
    level: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    id: str
    source_uri: str
    text: str
    sections: list[ParsedSection]
    metadata: dict[str, Any] = field(default_factory=dict)
    title: str | None = None


@dataclass
class Chunk:
    id: str
    document_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddedChunk(Chunk):
    embedding: list[float] = field(default_factory=list)
    embedding_model: str = ""


@dataclass
class RetrievalRequest:
    query: str
    top_k: int
    tenant_id: str | None = None
    filters: dict[str, Any] = field(default_factory=dict)
    score_threshold: float | None = None


@dataclass
class RetrievedChunk(Chunk):
    score: float = 0.0
    rerank_score: float | None = None


@dataclass
class Citation:
    source_uri: str
    title: str | None = None
    section: str | None = None
    page_number: int | None = None
    chunk_id: str | None = None


@dataclass
class RagContext:
    text: str
    chunks: list[RetrievedChunk]
    citations: list[Citation]
    token_count: int
```

```python
class DocumentLoader(Protocol):
    async def load(self, source: dict[str, Any]) -> list[RawDocument]:
        ...


class DocumentParser(Protocol):
    async def parse(self, document: RawDocument) -> ParsedDocument:
        ...


class Chunker(Protocol):
    async def chunk(self, document: ParsedDocument) -> list[Chunk]:
        ...


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class VectorStore(Protocol):
    async def upsert(self, chunks: list[EmbeddedChunk]) -> None:
        ...

    async def query(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        ...

    async def delete(self, filters: dict[str, Any]) -> None:
        ...


class Retriever(Protocol):
    async def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        ...


class Reranker(Protocol):
    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        ...


class ContextBuilder(Protocol):
    async def build(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        max_tokens: int,
    ) -> RagContext:
        ...
```

## 7. 設定檔格式

建議提供 YAML 或 JSON config。

```yaml
rag:
  tenant_id: default
  loader:
    type: local_directory
    path: ./docs
    include:
      - "**/*.md"
      - "**/*.pdf"
      - "**/*.html"
  parser:
    type: default
  chunker:
    type: recursive
    chunk_size: 800
    chunk_overlap: 120
    preserve_headings: true
  embedder:
    provider: openai
    model: text-embedding-3-small
    batch_size: 64
    cache: true
  vector_store:
    provider: qdrant
    collection: rag_documents
  retriever:
    strategy: dense
    top_k: 20
    score_threshold: 0.3
  reranker:
    type: none
  context:
    max_tokens: 6000
    mode: strict_citation
```

## 8. 實作里程碑

### Milestone 1：核心資料模型與本地 Pipeline

目標：建立最小可用 pipeline，能從本地 Markdown/TXT 建索引並查詢。

工作項目：

- 定義核心 types。
- 實作 local file loader。
- 實作 Markdown/TXT parser。
- 實作 recursive chunker。
- 實作 mock embedder。
- 實作 in-memory vector store。
- 實作 dense retriever。
- 實作 context builder。
- 建立基本單元測試。

驗收標準：

- 能匯入本地文件。
- 能產生 chunks。
- 能查詢 top-k chunks。
- 能輸出 context 與 citations。
- 測試覆蓋主要資料流。

### Milestone 2：真實 Embedding 與 Vector Store

目標：接入可用於 production-like demo 的 embedding provider 與 vector store。

工作項目：

- 實作 OpenAI embedder。
- 實作 embedding cache。
- 實作 Qdrant 或 pgvector adapter。
- 支援 metadata filter。
- 支援 tenant namespace。
- 加入 retry 與 rate limit。
- 補上整合測試。

驗收標準：

- 可將文件索引進真實 vector store。
- 可依 tenant 與 metadata 查詢。
- embedding model 與 dimension 被正確記錄。
- provider 失敗時有可理解的錯誤訊息。

### Milestone 3：Reranking、Trace 與引用

目標：讓結果可解釋、可 debug、可追溯。

工作項目：

- 實作 no-op 與 score-based reranker。
- 定義 trace schema。
- 所有 pipeline step 寫入 trace。
- 強化 citation 格式。
- context builder 支援 token budget。
- 支援相鄰 chunk 合併與去重。

驗收標準：

- 每次 query 都能輸出完整 trace。
- 答案 context 可回到來源 chunk。
- citation 包含 source URI、title、section、page。
- context 不超過設定 token budget。

### Milestone 4：權限、多租戶與同步

目標：支援企業或多用戶場景。

工作項目：

- 定義 ACL metadata。
- retrieval 加入 ACL filter。
- loader 支援 incremental sync。
- loader 支援 delete sync。
- 支援 document version。
- 加入 audit log。

驗收標準：

- 不同 tenant 的資料不會互相檢索。
- 使用者只能取得自己有權限的 chunks。
- 文件刪除後不會再被查到。
- 同步過程可重試且可觀測。

### Milestone 5：評估與品質改善

目標：建立可量化改善流程。

工作項目：

- 定義 eval dataset 格式。
- 實作 retrieval eval。
- 實作 citation correctness eval。
- 實作 answer faithfulness eval hook。
- 建立策略比較報告。
- 加入 benchmark command。

驗收標準：

- 可比較不同 chunking 參數。
- 可比較不同 embedding model。
- 可輸出 recall、precision、MRR、empty retrieval rate。
- CI 可執行核心 eval 或 smoke eval。

### Milestone 6：擴充資料來源與 Hybrid Search

目標：擴大可用性與搜尋品質。

工作項目：

- 實作 HTML parser 強化。
- 實作 PDF parser。
- 支援 BM25。
- 支援 hybrid search。
- 支援 query rewriting。
- 支援 multi-query retrieval。

驗收標準：

- PDF、HTML、Markdown 可進入同一 pipeline。
- hybrid search 能與 dense search 比較。
- query rewriting 可透過 config 開關。

## 9. 測試策略

單元測試：

- Loader：檔案篩選、metadata、錯誤處理。
- Parser：標題、段落、表格、空白清理。
- Chunker：chunk size、overlap、section path。
- Embedder：batch、cache、retry。
- Vector Store：upsert、delete、query、filter。
- Context Builder：token budget、去重、citation。

整合測試：

- 本地文件到 in-memory store。
- 本地文件到真實 vector store。
- 多租戶隔離。
- ACL filtering。
- delete sync。

評估測試：

- Golden QA retrieval recall。
- Citation correctness。
- Empty retrieval rate。
- Latency baseline。

## 10. 錯誤處理

錯誤應區分為：

- 使用者設定錯誤。
- 資料來源不可讀。
- 解析失敗。
- Embedding provider 失敗。
- Vector store 失敗。
- 權限或 tenant 設定錯誤。
- Context 超過 token budget。

每個錯誤至少包含：

- error code。
- message。
- failed step。
- retryable。
- trace id。

## 11. 安全與治理

第一版最低要求：

- Tenant isolation。
- Source URI allowlist。
- Metadata filter validation。
- Trace redaction。
- API key 不寫入 log。
- 文件內容中的指令不得直接覆蓋 system instruction。

後續強化：

- PII detection。
- PII redaction。
- Prompt injection classifier。
- Audit export。
- Retention policy。

## 12. API 設計

建議至少提供三類 API。

### Indexing API

```python
await rag.index(
    source={
        "type": "local_directory",
        "path": "./docs",
    },
    tenant_id="default",
)
```

### Retrieval API

```python
result = await rag.retrieve(
    query="如何設定權限過濾？",
    tenant_id="default",
    user_id="user_123",
    top_k=10,
)
```

### Answer API

```python
answer = await rag.answer(
    query="如何設定權限過濾？",
    tenant_id="default",
    user_id="user_123",
    mode="strict_citation",
)
```

## 13. 專案結構建議

```text
src/
  core/
    types.py
    errors.py
    config.py
  loaders/
    local_directory_loader.py
  parsers/
    markdown_parser.py
    text_parser.py
    html_parser.py
    pdf_parser.py
  chunkers/
    recursive_chunker.py
  embedders/
    mock_embedder.py
    openai_embedder.py
  vector_stores/
    memory_vector_store.py
    qdrant_vector_store.py
    pgvector_store.py
  retrieval/
    dense_retriever.py
    hybrid_retriever.py
  rerankers/
    noop_reranker.py
    score_reranker.py
  context/
    context_builder.py
    citations.py
  generation/
    generator.py
  observability/
    trace.py
    metrics.py
  eval/
    retrieval_eval.py
    answer_eval.py
```

## 14. 優先順序

建議先做：

1. 核心 types 與 config schema。
2. 本地 Markdown/TXT ingestion。
3. Recursive chunker。
4. Mock embedder 與 in-memory vector store。
5. Retrieval + context builder + citations。
6. OpenAI embedder。
7. Qdrant 或 pgvector。
8. Trace。
9. ACL 與 tenant filter。
10. Evaluation。

## 15. 主要風險

- Parser 品質不穩會直接影響 retrieval。
- Chunking 策略過度通用會犧牲特定文件品質。
- Metadata schema 若前期沒有固定，後續 migration 成本高。
- 沒有 trace 會讓 production debug 很困難。
- 沒有 eval 會讓改善只靠感覺。
- 權限過濾若不是 retrieval 層的一等公民，容易造成資料外洩。

## 16. 第一版完成定義

第一版完成時，應滿足：

- 可用 config 建立 RAG pipeline。
- 可匯入本地 Markdown/TXT 文件。
- 可切 chunk、embedding、寫入 in-memory vector store。
- 可替換成 OpenAI embedder。
- 可替換成至少一種真實 vector store。
- 可查詢並取得 top-k chunks。
- 可組裝 context。
- 可輸出 citations。
- 可輸出 trace。
- 有基本單元測試與整合測試。
