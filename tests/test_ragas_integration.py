import os

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("RAGAS_LIVE") != "1",
    reason="set RAGAS_LIVE=1 (with ragas installed and QWEN_* env) to run live ragas eval",
)


async def test_ragas_end_to_end():
    pytest.importorskip("ragas")
    pytest.importorskip("langchain_openai")

    from rag_adapter.config import load_config
    from rag_adapter.factory import build_query_pipeline, build_ragas_judge
    from rag_adapter.evaluation.ragas_eval import RagasCase, collect_samples, evaluate_with_ragas

    config = load_config("examples/rag.yaml")  # 需 query.generation.enabled=true 與 QWEN_* 環境變數
    pipeline = build_query_pipeline(config)
    llm, embeddings = build_ragas_judge(config)

    samples = await collect_samples(pipeline, [RagasCase(question="如何請假?", ground_truth="提前三天於系統申請")])
    result = evaluate_with_ragas(samples, config.evaluation.metrics, llm, embeddings)

    assert result is not None
