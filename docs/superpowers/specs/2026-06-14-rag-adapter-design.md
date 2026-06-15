# RAG Adapter — 詳細規格書

> 狀態:Draft · 日期:2026-06-14 · 分支:rag
> 本文件是 `spec.md` 的細化版,作為後續實作計畫(implementation plan)的依據。

---

## 1. 定位與目標

提供一套 **Python library(SDK)**,把**完整 RAG 流程(R-A-G 三段齊全:Retrieve → Augment → Generate)**拆成**穩定介面 + 可替換實作**,讓不同團隊用最少程式碼裝出可用 pipeline,並能逐層替換模型 / 向量庫 / 資料來源 / 檢索策略 / LLM;同時每次查詢都可回溯、可離線評估。

SDK 涵蓋從資料接入到**最終答案生成**:Loader → … → ContextBuilder → **PromptBuilder → Generator(LLM Answer)**,並附引用與分數。

### 交付形態
- **Python Library / SDK**(`pip` 安裝,各專案 import 後在自己的程式內組裝 pipeline)。
- 不在 v1 提供獨立 service / API 封裝(未來可選)。

### 框架依賴策略
- **以自訂輕量介面為骨架**(各層用 `Protocol` 定義),不綁定 LangChain。
- **僅在少數「輪子成熟」的層,於 adapter 實作內部選用 LangChain**:Chunker(TextSplitter)、VectorStore(`langchain-qdrant`)、BM25(`BM25Retriever`)。
- 核心差異化(統一介面、ContextBuilder、PromptBuilder、Generator、引用追溯、Langfuse 觀測、評估)**一律自寫**,不經 LangChain。
- 不使用 LangGraph(Non-Goal:複雜 agent workflow)。

---

## 2. 四大支柱目標與驗收

### A. Replaceable 可替換(v1 核心)
- 每一層以 `Protocol` 定義穩定介面,實作可獨立抽換而不動到呼叫端。
- 替換任一 provider(含 LLM)只需注入不同實作或改設定,**不需改 pipeline 結構**。
- **驗收**:用同一份 query 程式碼,把 Embedder 或 Generator 從 Qwen 換成另一個實作(含 mock),其餘程式不變即可運作。

### B. Quick-Start 開箱即用(v1 核心)
- 提供一組預設**端到端** pipeline:
  `html/json/xml/tkms loader → parser → chunker → Qwen embedder → Qdrant → (cosine/BM25) retriever → fusion → Qwen reranker → context builder → prompt builder → Qwen generator`。
- **驗收**:**10–20 行內**完成「建索引 + 提問 + 拿到帶引用的答案」最小範例,並附可執行 example。

### C. Observability 可觀測(v1 接基本 trace)
- 每次查詢可回溯:命中的來源文件、chunk、各階段分數、重排前後排序、最終組裝的 context、送進 LLM 的 prompt、生成的答案與引用。
- 透過既有 **Langfuse SDK** 輸出 trace;觀測為**可插拔**,關閉時不影響主流程。
- **驗收**:跑一次查詢後,可在 Langfuse 看到含 generation 的完整 trace 與各階段中繼資料。

### D. Evaluation 可評估(v1 先做 Retrieval 指標 + 介面預留)
- 離線評估三類指標:
  - **Retrieval**:recall@k、precision@k、MRR、nDCG
  - **Context 品質**:context relevance、是否含黃金段落
  - **Answer quality**:faithfulness、answer relevance —— 直接評估**產品 pipeline 實際生成的答案**;faithfulness / relevance 的判分使用可設定的 **judge LLM**(可與生成用 LLM 不同)
- 吃一份標註資料集(query → 期望文件 / 段落 [→ 參考答案]),輸出可比較不同策略的報告。
- **驗收(v1)**:能對標註集算出 Retrieval 指標並輸出報告;Context 品質與 Answer quality 介面預留、列為 v1 之後。

---

## 3. 元件架構

```
Indexing:  Loader → Parser → Chunker → Embedder → VectorStore(含 upsert/delete)
Query:     [QueryTransform?] → Retriever(cosine / BM25) → Fusion(RRF) → Reranker
           → ContextBuilder(含 citation) → PromptBuilder → Generator(LLM Answer)
貫穿:      Document / Chunk 資料模型
橫切:      Observability(Langfuse) · Evaluation(離線)
```

### 各層職責與邊界

| 層 | 職責 | v1 內建實作 |
|---|---|---|
| **Loader** | 取得原始 bytes / 連到資料來源 | html、tkms、json、xml |
| **Parser** | 從格式抽出乾淨文字 + 結構 / metadata | 對應上述格式 |
| **Chunker** | 切分文字(可內部用 LangChain TextSplitter) | recursive / token-based |
| **Embedder** | 文字 → 向量 | Qwen |
| **VectorStore** | 向量寫入 / 查詢,**含 upsert / delete / 重建** | Qdrant |
| **QueryTransform**(可選) | 查詢前處理(rewrite/expansion/HyDE) | 僅 pass-through,介面預留 |
| **Retriever** | 取回候選 | cosine_similarity、BM25 |
| **Fusion** | 合併多路檢索結果 | RRF(Reciprocal Rank Fusion) |
| **Reranker** | 重排候選 | Qwen |
| **ContextBuilder** | 去重、token 預算、組裝 context、**產出引用** | 預設組裝策略 |
| **PromptBuilder** | 以 template 把 query + context(+ 引用標記)組成 prompt | 預設可覆寫 template |
| **Generator** | 呼叫 LLM 生成答案,回傳答案 + 引用 | Qwen;提供 `generate()` 與 `stream()` |

> **Loader vs Parser 邊界**:Loader 只負責「取得 / 連線」,Parser 只負責「解析 / 抽取」。不可在 Loader 內做格式解析。

### 關鍵設計重點

1. **Fusion 為必要層**:同時使用 cosine + BM25 時,需 RRF 或加權融合,排在 Retriever 之後、Reranker 之前。
2. **Document / Chunk 資料模型是貫穿全程的契約**:統一 schema(`id / text / metadata / embedding / score / source_ref / position`)。引用與 Observability 回溯皆依賴它。引用不是獨立元件,而是 ContextBuilder 依 `source_ref` 產出,並由 PromptBuilder / Generator 帶入答案。
3. **VectorStore 介面包含 upsert / delete**:支援增量更新與重建,避免每次整庫重建。
4. **QueryTransform 僅預留介面**:v1 不實作策略(符合 Non-Goal:不做複雜 agent workflow)。
5. **PromptBuilder 與 Generator 解耦**:PromptBuilder 只負責「組 prompt」,Generator 只負責「呼叫 LLM」,兩者皆可獨立替換。template 可由呼叫端覆寫。
6. **Generator 雙模式**:`generate()` 回傳完整答案字串 + 引用;`stream()` 回傳逐 token 串流。Observability 需同時涵蓋兩條路徑。
7. **Evaluation 為離線橫切流程**,非 query pipeline 的一步;Answer quality 直接評估產品生成的答案。

---

## 4. v1 範圍邊界

**v1 必做(完整 RAG 功能)**
- A(Replaceable)+ B(Quick-Start)完整,且 pipeline **端到端到答案生成**
- Fusion(RRF)與 Document/Chunk 資料模型(Replaceable 的地基)
- VectorStore 的 upsert / delete
- PromptBuilder + Generator(含 `generate()` 與 `stream()`)
- C:接上 Langfuse 基本 trace(含 generation)
- D:Retrieval 指標 + 評估介面預留

**v1 之後**
- D 的 Context 品質與 Answer quality(judge LLM 判分)
- QueryTransform 實際策略
- 更多 Loader 格式
- 各層的 LangChain adapter 擴充
- 可選的 service / API 封裝層

---

## 5. Non-Goal

- 複雜 agent workflow
- 建置知識圖譜
- 所有檔案格式的完美解析
- 完全自動的 prompt injection 判定

---

## 6. 技術約束

- Python 3.10+
- 各層以 `Protocol` 定義介面,搭配依賴注入組裝 pipeline
- 型別註記從簡:僅在需要時標註 `dict` / `list`,不引入 `typing` imports、不標註基本型別
- 觀測與評估皆為可插拔,預設不開啟也能跑主流程
- Generator 支援一次性與 streaming 兩種輸出

---

## 7. Design Patterns

1. **Interface-Driven**:所有模組透過 `Protocol` 定義介面,實作可替換。
2. **Type-First**:資料結構以 dataclass 定義(`models.py`)。本專案採「最小型別註記」——資料層用 dataclass 即達標,函式簽章不強制標型別。
3. **Async-First(僅 I/O 層)**:有 I/O 的層(Loader / Embedder / VectorStore / Retriever / Reranker / Generator)以 `async/await` 實作;純 CPU 層(Parser / Chunker / Fusion / ContextBuilder / PromptBuilder / QueryTransform)維持同步。Pipeline 於 I/O 步驟 `await`,`Generator.stream` 為 async generator。
4. **Config-Driven**:透過 YAML 配置選擇各層 provider 與參數,由 config 工廠組裝 pipeline;secrets 以環境變數插值。
5. **Pipeline**:`IndexingPipeline` / `QueryPipeline` 串接元件。

> 套用順序:先重構已完成的 P1/P2 達成上述 patterns,再以新標準寫 P3–P5。
