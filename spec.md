# RAG Adapter 

## Goal
設計並實作一個可供多數專案使用的 RAG Adapter。它應該把資料接入、解析、切分、Embedding、索引、檢索、重排、上下文組裝、引用、觀測與治理抽象成可替換模組，讓不同團隊能依需求替換模型、向量庫、資料來源與檢索策略。

- Quick-Start 開箱即用：提供一組預設 pipeline，能快速支援常見文件與向量庫
- Replaceable 可替換：各層模組以穩定 interface 串接，不綁死特定 provider
- Evaluation 可評估：內建 retrieval 與 answer quality 的離線評估流程
- Observability 可觀測性：每次回答都能回溯來源文件、chunk、分數與組裝後 context
    - 目前已有團隊基於 Langfuse 創建 SDK 可使用

## Non-Goal
- 複雜 agent workflow
- 建置知識圖譜
- 所有檔案格式的完美解析
- 完全自動的 prompt injection 判定

---

## Pipeline & Components

### Indexing Pipeline

Data Loader (current supports: html, tkms, json, xml)
Parser
Chunker
Embedder (current supports: Qwen Model)
Vector Store (current supports: Qrant)

### Query Pipeline
- Retirever (cosine_similarity, BM25)
- Reranker (current supports: Qwen Model)
- Context Builder
- Evaluation

---

## Design Pattern

1. **Interface-Driven**：所有模組透過 Protocol 定義介面，實作可替換
2. **Type-First**：使用 dataclass/Pydantic 定義資料結構
3. **Async-First**：所有 I/O 操作使用 async/await
4. **Config-Driven**：透過 YAML 配置調整行為
5. **Pipeline**: 透過 Pipeline 串接元件

---

## LangChain 使用評估 
| 元件 | LangChain 現成能力 | 建議 |
| :--- | :--- | :--- |
| **Data Loader** <br>`(html/json/xml/tkms)` | `DocumentLoaders` 支援相當豐富 (包含 html/json/xml)，但 `tkms` 為內部特有來源，LangChain 並未原生支援。 | **自訂介面**。<br>html/json/xml 可封裝 LangChain loader，而 `tkms` 則自行實作。 |
| **Parser** | 提供基礎的 `Document` 資料結構與部分 `transformer` 工具。 | **自訂為主**，可選擇性參考或沿用其資料結構。 |
| **Chunker** | `TextSplitter` 系列功能成熟且健全 (如 recursive、markdown、token-based 等)。 | **值得直接借用**，並在 SDK 內自行包裝一層抽象介面。 |
| **Embedder** `(Qwen)` | 提供標準的 `embeddings` 抽象介面；但 Qwen 需走 OpenAI-compatible 相容層或自行實作。 | **自訂介面**，並實作 Qwen 的 Adapter。 |
| **Vector Store** `(Qdrant)` | 與 Qdrant 整合作業相當成熟 (`langchain-qdrant`)。 | **值得借用**，但務必使用 SDK 自身的 interface 包覆，避免底層技術鎖死 (Vendor Lock-in)。 |
| **Retriever** <br>`(cosine/BM25)` | Cosine 檢索走 vectorstore；`BM25Retriever` 為現成元件；並提供 `EnsembleRetriever` 進行混合檢索。 | **可借用現成元件**，但多路召回與混合（Hybrid）策略建議由 SDK 自行控管。 |
| **Reranker** `(Qwen)` | 雖然有設計 `reranker` 的抽象介面，但 Qwen reranker 仍需自行對接。 | **自訂實作**。 |
| **Context Builder** | LangChain 幾乎沒有對應的元件（此部分通常為團隊的核心業務價值所在）。 | **自主開發**。 |
| **Evaluation** | LangChain 在此領域生態較弱；業界目前多採用 Ragas 或選擇自建。 | **自主開發** 或 考慮對接 **Ragas** 生態。 |
| **Observability** | 團隊目前已有整合 Langfuse SDK，其靈活性與客製化程度比 LangSmith 更貼近當前需求。 | **直接採用 Langfuse**，不需額外透過 LangChain 轉接。 |