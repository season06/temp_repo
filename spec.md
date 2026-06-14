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
- Prompt Builder & LLM Answer

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

## Architecture

- Python 3.10+
- 合適的 Design Pattern 
- 是否需要使用 LangChain / LangGraph ?

---

## Phase

- phase 1 : MVP Workable
- phase 2 : 提升搜尋品質
- phase 3 : 可上線品質