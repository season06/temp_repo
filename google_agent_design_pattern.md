Google Agent Design Patterns 介紹

Google 在多份白皮書（如 Agents、Agents Companion）與 Agent Development Kit (ADK) 中，整理了一套建構 LLM Agent 的設計模式。以下分層說明。
業界框架（如 OWASP LLM Top 10、Google Secure AI Framework SAIF）

一、Agent 的核心三要素

Google 對 agent 的定義是：在「模型 (Model)」之外，加上工具 (Tools) 與編排層 (Orchestration Layer)。

┌───────────────┬────────────────────────────────────────────────────────────────────────────────┐
│     元件      │                                      角色                                      │
├───────────────┼────────────────────────────────────────────────────────────────────────────────┤
│ Model         │ 推理核心（LLM），負責決策與語言理解                                            │
├───────────────┼────────────────────────────────────────────────────────────────────────────────┤
│ Tools         │ 與外部世界互動：API、Function、資料檢索 (Extensions / Functions / Data Stores) │
├───────────────┼────────────────────────────────────────────────────────────────────────────────┤
│ Orchestration │ 控制「觀察→推理→行動」的循環，管理狀態與記憶                                   │
└───────────────┴────────────────────────────────────────────────────────────────────────────────┘

二、單一 Agent 的推理模式 (Reasoning Frameworks)

這些是 orchestration layer 內部的「思考」方式：

- ReAct (Reason + Act) — 交錯進行「推理」與「行動」，每次行動後觀察結果再決定下一步。最常用。
- Chain-of-Thought (CoT) — 逐步推理，適合需要中間步驟的任務。
- Tree-of-Thoughts (ToT) — 探索多條推理分支，適合策略性/探索性任務。

三、多 Agent 設計模式 (Multi-Agent Patterns)

這是 ADK 的重點，把複雜系統拆成協作的多個 agent：

1. Coordinator / Dispatcher（協調者）
一個中央 agent 把任務路由給專責的 sub-agent。
2. Sequential（順序管線）
Agent 串成 pipeline，前一個的輸出餵給下一個（類似 workflow）。
3. Parallel（平行扇出）
多個 agent 同時處理子任務，最後彙整結果。
4. Hierarchical（階層式）
Manager agent 管理 worker agents，形成樹狀結構，可逐層分解。
5. Iterative / Loop（迭代精煉）
Generator + Critic 反覆迴圈，逐步改善輸出（如「生成→評審→修正」）。
6. Human-in-the-loop
在關鍵決策點插入人類審核。

四、生產化的支援模式 (Agent Ops)

Agents Companion 強調落地時還需要：

- Memory — 短期（session/context）與長期（向量庫）記憶。
- Evaluation — 不只評最終答案，還評軌跡 (trajectory)：工具選對了嗎？步驟順序對嗎？
- RAG / Agentic RAG — 讓 agent 主動決定何時、如何檢索。
- Guardrails — 安全與權限邊界控制。