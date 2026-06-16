from dataclasses import dataclass


@dataclass
class RagasCase:
    """RAGAS 評估的一筆輸入:問題與選配的標準答案(context_recall / correctness 需要)。"""
    question: str
    ground_truth: str = ""


async def collect_samples(pipeline, cases):
    """跑 query pipeline,為每個 case 收集 RAGAS 需要的欄位。

    pipeline 需提供 async retrieve(query) -> list[RetrievedChunk] 與 async answer(query) -> Answer。
    """
    samples = []
    for case in cases:
        reranked = await pipeline.retrieve(case.question)
        answer = await pipeline.answer(case.question)
        samples.append({
            "question": case.question,
            "answer": answer.text,
            "contexts": [rc.chunk.text for rc in reranked],
            "ground_truth": case.ground_truth,
        })
    return samples


def _resolve_metrics(names):
    # 版本適配點:依安裝的 ragas 版本調整匯入
    from ragas.metrics import (
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    )

    table = {
        "faithfulness": faithfulness,
        "answer_relevancy": answer_relevancy,
        "context_precision": context_precision,
        "context_recall": context_recall,
    }
    return [table[name] for name in names]


def evaluate_with_ragas(samples, metric_names, llm, embeddings):
    """以 RAGAS 對收集到的樣本評分。llm / embeddings 為 RAGAS 相容物件(見 factory.build_ragas_judge)。

    回傳 RAGAS 的結果物件(各指標分數)。
    """
    # 版本適配點:依安裝的 ragas 版本調整匯入
    from datasets import Dataset
    from ragas import evaluate

    dataset = Dataset.from_dict({
        "question": [s["question"] for s in samples],
        "answer": [s["answer"] for s in samples],
        "contexts": [s["contexts"] for s in samples],
        "ground_truth": [s["ground_truth"] for s in samples],
    })
    return evaluate(dataset, metrics=_resolve_metrics(metric_names), llm=llm, embeddings=embeddings)
