# RAG Adapter 使用手冊

## 1. 目前狀態

這個 RAG Adapter 目前是第一版 skeleton，已可跑通以下流程：

```text
local files
  -> loader
  -> parser
  -> chunker
  -> embedder
  -> vector store
  -> retriever
  -> reranker
  -> context builder
```

預設元件：

- Loader：`LocalDirectoryLoader`
- Parser：`TextParser`
- Chunker：`RecursiveChunker`
- Embedder：`MockEmbedder`
- Vector store：`MemoryVectorStore`
- Retriever：`DenseRetriever`
- Reranker：`NoopReranker`
- Tracer：`NullTracer`

因此目前不需要地端 Qwen 服務，也能先測試 ingestion、retrieval 與 context assembly。

## 2. 專案結構

```text
RAG/
  pyproject.toml
  implementation-plan.md
  tech-stack.md
  usage-guide.md
  src/
    rag_adapter/
      pipeline.py
      core/
      loaders/
      parsers/
      chunkers/
      embedders/
      vector_stores/
      retrieval/
      rerankers/
      context/
      observability/
  tests/
    test_pipeline.py
```

主要入口：

- `rag_adapter.RagAdapter`

## 3. 環境需求

建議：

- Python 3.12+

目前測試環境也已用 Python 3.13 跑過。

若只使用預設 mock pipeline，核心流程不需要額外服務。

正式 tech stack 會使用：

- Qwen embedding model，dimension `4096`
- Qwen reranker model
- Langfuse，透過既有自製 SDK
- LangChain / LangGraph optional integration
- Qdrant 或 pgvector，後續接正式 vector store adapter

## 4. 安裝與執行

進入 `RAG` 目錄：

```bash
cd /path/to/RAG
```

若尚未安裝成 package，可先設定 `PYTHONPATH`：

```bash
export PYTHONPATH=src
```

執行測試：

```bash
python -m pytest
```

目前預期結果：

```text
2 passed
```

## 5. 快速開始

專案已提供 demo script 與範例文件，可直接執行：

```bash
cd /path/to/RAG
python main.py
```

Demo 會讀取 `demo_docs/`，展示三個情境：

- Qwen embedding dimension。
- Langfuse observability。
- Tenant isolation。

若要自行建立最小範例，可參考下方步驟。

建立資料夾：

```text
RAG/
  docs/
    intro.md
```

範例文件 `docs/intro.md`：

```markdown
# RAG Adapter

Qwen embedding model 使用 4096 維向量。

Langfuse 會記錄 query、retrieval、rerank 與 context trace。
```

建立 `examples/basic_usage.py`：

```python
import asyncio

from rag_adapter import RagAdapter


async def main() -> None:
    rag = RagAdapter()

    chunks = await rag.index(
        source={
            "type": "local_directory",
            "path": "./docs",
            "suffixes": [".md", ".txt"],
        },
        tenant_id="default",
    )
    print(f"indexed chunks: {len(chunks)}")

    results = await rag.retrieve(
        query="Qwen embedding 維度是多少？",
        tenant_id="default",
        top_k=5,
    )

    for result in results:
        print("score:", result.score)
        print("source:", result.metadata.get("source_uri"))
        print(result.text)
        print()


asyncio.run(main())
```

執行：

```bash
export PYTHONPATH=src
python examples/basic_usage.py
```

## 6. Index 文件

使用 `index()` 將本地文件載入並寫入 vector store。

```python
chunks = await rag.index(
    source={
        "type": "local_directory",
        "path": "./docs",
        "suffixes": [".md", ".txt"],
    },
    tenant_id="default",
)
```

參數：

- `source["type"]`：目前支援 `local_directory`。
- `source["path"]`：文件資料夾。
- `source["suffixes"]`：要讀取的副檔名，預設為 `.md` 與 `.txt`。
- `tenant_id`：租戶 ID，會寫入 chunk metadata，retrieval 時會用來隔離資料。

回傳：

- `list[Chunk]`

目前 loader 會讀取：

- Markdown
- TXT

## 7. Retrieve 文件

使用 `retrieve()` 搜尋相關 chunks。

```python
results = await rag.retrieve(
    query="如何使用 Langfuse trace？",
    tenant_id="default",
    top_k=5,
)
```

回傳：

- `list[RetrievedChunk]`

每個 `RetrievedChunk` 包含：

- `id`
- `document_id`
- `text`
- `metadata`
- `score`
- `rerank_score`

範例：

```python
for item in results:
    print(item.score)
    print(item.rerank_score)
    print(item.metadata.get("source_uri"))
    print(item.text)
```

## 8. 使用 Metadata Filter

`retrieve()` 支援簡單 metadata filter。

```python
results = await rag.retrieve(
    query="Qwen reranker",
    tenant_id="default",
    filters={
        "suffix": ".md",
    },
)
```

目前 filter 是 exact match。

## 9. Answer 與 Citation

使用 `answer()` 取得 context 與 citations。

```python
answer = await rag.answer(
    query="Qwen embedding 維度是多少？",
    tenant_id="default",
    user_id="user_123",
)

print(answer.answer)
print(answer.trace_id)
```

目前 `answer()` 是 extractive 版本，會直接回傳組裝後 context，尚未接生成模型。

取得 citations：

```python
for citation in answer.context.citations:
    print(citation.source_uri)
    print(citation.title)
    print(citation.chunk_id)
```

## 10. 自訂 Config

可以建立 `RagConfig` 調整 chunking、retrieval、reranking 與 context token budget。

```python
from rag_adapter import RagAdapter
from rag_adapter.core.config import (
    ChunkerConfig,
    ContextConfig,
    RagConfig,
    RetrieverConfig,
    RerankerConfig,
)


config = RagConfig(
    tenant_id="default",
    chunker=ChunkerConfig(
        chunk_size=1000,
        chunk_overlap=150,
    ),
    retriever=RetrieverConfig(
        top_k=20,
        score_threshold=0.2,
    ),
    reranker=RerankerConfig(
        top_n=8,
    ),
    context=ContextConfig(
        max_tokens=6000,
    ),
)

rag = RagAdapter(config=config)
```

Qwen embedding dimension 有固定驗證：

```python
from rag_adapter.core.config import EmbedderConfig


EmbedderConfig(
    provider="qwen",
    model="qwen-embedding",
    dimension=4096,
)
```

若 `provider="qwen"` 且 `dimension` 不是 `4096`，會丟出 `ValueError`。

## 11. 接地端 Qwen Embedding

目前已提供 `QwenEmbedder` adapter skeleton。

```python
from rag_adapter import RagAdapter
from rag_adapter.embedders.qwen_embedder import QwenEmbedder


embedder = QwenEmbedder(
    endpoint_url="http://localhost:8000/v1/embeddings",
    model_name="qwen-embedding",
)

rag = RagAdapter(embedder=embedder)
```

Qwen embedding endpoint 預期格式：

Request：

```json
{
  "model": "qwen-embedding",
  "input": ["text 1", "text 2"]
}
```

Response：

```json
{
  "data": [
    {"embedding": [0.1, 0.2]},
    {"embedding": [0.3, 0.4]}
  ]
}
```

正式 Qwen embedding response 的每個 embedding 長度必須是 `4096`。

## 12. 接地端 Qwen Reranker

目前已提供 `QwenReranker` adapter skeleton。

```python
from rag_adapter import RagAdapter
from rag_adapter.rerankers.qwen_reranker import QwenReranker


reranker = QwenReranker(
    endpoint_url="http://localhost:8001/rerank",
    model_name="qwen-reranker",
)

rag = RagAdapter(reranker=reranker)
```

Qwen reranker endpoint 預期格式：

Request：

```json
{
  "model": "qwen-reranker",
  "query": "question",
  "documents": [
    {"id": "chunk_1", "text": "document text"}
  ]
}
```

Response：

```json
{
  "results": [
    {"id": "chunk_1", "score": 0.95}
  ]
}
```

Reranker 會保留原始 `retrieval_score`，並將模型分數寫入 `rerank_score`。

## 13. 接 Langfuse 自製 SDK

目前提供 `LangfuseSdkTracer` wrapper。它假設自製 SDK 有三個 async method：

- `start_trace(trace_id, name, metadata)`
- `add_event(trace_id, name, metadata)`
- `end_trace(trace_id, output, error)`

用法：

```python
from rag_adapter import RagAdapter
from rag_adapter.observability.tracer import LangfuseSdkTracer


tracer = LangfuseSdkTracer(sdk=internal_langfuse_sdk)
rag = RagAdapter(tracer=tracer)
```

目前 pipeline 會記錄：

- `rag.index`
- indexed document/chunk count
- `rag.answer`
- selected chunk count
- context token count
- citation count

後續應擴充：

- retrieval candidates
- retrieval scores
- rerank scores
- selected chunks
- latency
- error

## 14. 多租戶隔離

Index 時指定 `tenant_id`：

```python
await rag.index(
    source={"type": "local_directory", "path": "./docs_a"},
    tenant_id="tenant-a",
)
```

Retrieve 時也指定同一個 `tenant_id`：

```python
results = await rag.retrieve(
    query="查詢內容",
    tenant_id="tenant-a",
)
```

`MemoryVectorStore` 會用 chunk metadata 中的 `tenant_id` 做隔離。

## 15. 測試

執行：

```bash
cd /path/to/RAG
python -m pytest
```

目前測試涵蓋：

- local file index。
- retrieve。
- tenant metadata。
- Qwen embedding dimension validation。

## 16. 目前限制

目前尚未完成：

- Qdrant vector store adapter。
- pgvector adapter。
- 真正的 LLM answer generator。
- PDF parser。
- HTML parser。
- Markdown heading-aware parser。
- LangChain / LangGraph integration。
- 完整 Langfuse trace schema。
- ACL filter。
- retrieval eval。

目前 `answer()` 是 extractive context 回傳，不會生成自然語言總結。

## 17. 建議下一步

建議實作順序：

1. Qdrant vector store adapter。
2. Qwen endpoint integration test。
3. Langfuse trace schema 補完整。
4. Markdown heading-aware chunker。
5. PDF parser。
6. Retrieval eval。
7. LangChain / LangGraph optional wrapper。
