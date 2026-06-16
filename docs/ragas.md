 1. 它在量什麼:四個經典指標

  每筆樣本通常包含 question、answer(你 RAG 產生的)、contexts(檢索回的段落)、選配 ground_truth(標準答案)。

  ┌──────────────────────┬──────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────┬────────────────────────────────────────┬───────────────────┐
  │         指標         │            量什麼            │                                       怎麼算(直覺)                                        │           需要 ground_truth?           │   對應我們的層    │
  ├──────────────────────┼──────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────┼───────────────────┤
  │ Faithfulness(忠實度) │ 答案有沒有幻覺               │ 把答案拆成多個 claim,逐一問裁判「這能由 context 推出嗎」;分數 = 被支持的 claim / 總 claim │ 否                                     │ Answer            │
  ├──────────────────────┼──────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────┼───────────────────┤
  │ Answer Relevancy     │ 答案有沒有回到題上           │ 由答案反生成 N 個問題,算這些問題與原問題的 embedding 相似度                               │ 否                                     │ Answer            │
  ├──────────────────────┼──────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────┼───────────────────┤
  │ Context Precision    │ 相關段落有沒有排在前面       │ 逐段判相關性,獎勵「相關的排前面」(類似加權 precision)                                     │ 視版本(有 with/without reference 變體) │ Retrieval/Context │
  ├──────────────────────┼──────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────┼───────────────────┤
  │ Context Recall       │ 回答需要的資訊是否都被檢索到 │ 把 ground_truth 拆成 claim,檢查每個能否在 context 中找到                                  │ 是                                     │ Retrieval/Context │
  └──────────────────────┴──────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────────┴────────────────────────────────────────┴───────────────────┘

  新版另有 Factual Correctness / Answer Correctness(比對標準答案的事實+語意)、Context Entity Recall、Noise Sensitivity(對雜訊的敏感度)、以及 aspect critique(無害性等)。

  ---
  2. 運作原理

  - 兩個依賴:一個 judge LLM(打分用)和一個 embedding model(算相似度用)——都要你自己配置(支援包裝 LangChain / LlamaIndex 的模型,或自訂)。
  - LLM-as-judge:Faithfulness/Relevancy 靠 LLM 拆 claim、判斷,而非規則。
  - Reference-free:Faithfulness、Answer Relevancy、(部分)Context Precision 不需標準答案;只有 Context Recall / Correctness 需要 ground_truth。
  - 還附 synthetic test-set generation:能從你的文件自動生成 query→段落 測試集,降低標註成本。

  ---
  3. 最小範例(經典 API)

  from datasets import Dataset
  from ragas import evaluate
  from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall

  data = {
      "question":     ["如何請假?"],
      "answer":       ["依規定提前三天於系統申請……"],   # 你的 RAG 產出
      "contexts":     [["請假需於三日前申請……", "特休辦法……"]],  # 檢索回的段落
      "ground_truth": ["需提前三天於 HR 系統提出申請"],   # 給 context_recall 用
  }
  result = evaluate(Dataset.from_dict(data),
                    metrics=[faithfulness, answer_relevancy, context_precision, context_recall])
  print(result)   # {'faithfulness': 0.92, 'answer_relevancy': 0.88, ...}

  ---
  4. 優缺點

  優點
  - 標準化、社群大、文件多;reference-free 省標註。
  - 同時涵蓋檢索與生成品質;整合 LangChain/LlamaIndex/Langfuse。
  - 內建測試集生成。

  要注意
  - 成本/延遲/不穩定:每筆要跑數次 LLM;即使 temperature=0 仍有變異。小資料集分數會抖——建議題數夠多、多次取平均。
  - 裁判品質決定一切:judge LLM 的能力與偏誤直接影響分數;跨版本/跨模型分數不可直接比較。
  - claim 拆解品質會影響 Faithfulness。

  ---
  5. 它和我們 adapter 的關係
  
  我們自建的 evaluation 是 Retrieval 層(recall@k / precision@k / MRR / nDCG,用 golden chunk id,確定性、零成本)——適合每次改 retriever 就跑的回歸測試。

  RAGAS 補的是另兩層:用 LLM 裁判評 Faithfulness / Answer Relevancy / Context Precision/Recall。因為我們 pipeline 已經產出 question / answer / contexts / citations(P4 完成),要接 RAGAS 只需:

  QueryPipeline.answer() →  收集 {question, answer, contexts, [ground_truth]}
                         →  組成 RAGAS dataset → evaluate(metrics=[...])
  judge LLM 可重用 QwenGenerator 的 chat 端點(包一層 RAGAS 的 LLM 介面)

  分工建議:retrieval 回歸用我們的確定性指標(快、可進 CI);答案品質用 RAGAS 定期跑(慢、花 token)。兩者分層歸因——Recall 高但 Faithfulness 低 → 問題在生成而非檢索。