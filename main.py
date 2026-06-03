from __future__ import annotations

import asyncio
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from rag_adapter import RagAdapter  # noqa: E402
from rag_adapter.core.config import (  # noqa: E402
    ChunkerConfig,
    ContextConfig,
    RagConfig,
    RetrieverConfig,
    RerankerConfig,
)


SCENARIOS = [
    {
        "title": "Qwen embedding dimension",
        "query": "Qwen embedding 4096 dimension",
        "description": "查詢地端 Qwen embedding 的向量維度設定。",
    },
    {
        "title": "Langfuse observability",
        "query": "Langfuse observability internal SDK normalized query latency error",
        "description": "查詢 RAG Adapter 應該紀錄哪些 trace 欄位。",
    },
    {
        "title": "Tenant isolation",
        "query": "tenant isolation ACL metadata filter",
        "description": "查詢多租戶隔離與 ACL metadata filter 的設計。",
    },
]


async def main() -> None:
    config = RagConfig(
        tenant_id="demo",
        chunker=ChunkerConfig(chunk_size=700, chunk_overlap=80),
        retriever=RetrieverConfig(top_k=5),
        reranker=RerankerConfig(top_n=3),
        context=ContextConfig(max_tokens=1200),
    )
    rag = RagAdapter(config=config)

    docs_path = PROJECT_ROOT / "demo_docs"
    chunks = await rag.index(
        source={
            "type": "local_directory",
            "path": str(docs_path),
            "suffixes": [".md", ".txt"],
        },
        tenant_id="demo",
    )

    print_header("RAG Adapter Demo")
    print(f"Documents path: {docs_path}")
    print(f"Indexed chunks: {len(chunks)}")

    for scenario in SCENARIOS:
        await run_scenario(rag, scenario)


async def run_scenario(rag: RagAdapter, scenario: dict[str, str]) -> None:
    print_header(scenario["title"])
    print(f"Scenario: {scenario['description']}")
    print(f"Query: {scenario['query']}")

    results = await rag.retrieve(
        query=scenario["query"],
        tenant_id="demo",
        top_k=5,
    )

    print("\nTop retrieved chunks:")
    for index, item in enumerate(results, start=1):
        source = item.metadata.get("file_name") or item.metadata.get("source_uri")
        print(f"{index}. score={item.score:.4f} source={source}")
        print(indent(preview(item.text)))

    answer = await rag.answer(
        query=scenario["query"],
        tenant_id="demo",
        user_id="demo_user",
        top_k=5,
    )

    print("\nContext answer:")
    print(indent(preview(answer.answer, max_length=900)))
    print("\nCitations:")
    for citation in answer.context.citations:
        print(f"- {citation.title or 'Untitled'} | {citation.source_uri} | chunk={citation.chunk_id}")
    print(f"\nTrace ID: {answer.trace_id}")


def print_header(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def preview(text: str, max_length: int = 420) -> str:
    clean = " ".join(text.split())
    if len(clean) <= max_length:
        return clean
    return clean[: max_length - 3] + "..."


def indent(text: str, prefix: str = "  ") -> str:
    return "\n".join(f"{prefix}{line}" for line in text.splitlines())


if __name__ == "__main__":
    asyncio.run(main())
