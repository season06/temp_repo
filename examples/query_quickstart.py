"""Query pipeline 快速上手範例。

兩種用法:

1) 程式組裝(本檔 main,可直接執行,無需外部服務)
   先索引一份文件到 in-memory store,再以真實的 retriever / fusion / context builder
   組裝 query pipeline,示範 retrieve_context、answer 與 stream:

       python examples/query_quickstart.py

2) Config 驅動(正式環境,需 Qdrant server + Qwen API)
   見檔尾 `run_from_config`,搭配 examples/rag.yaml。
"""

import asyncio
import tempfile
from pathlib import Path

from rag_adapter.pipeline.indexing import IndexingPipeline
from rag_adapter.pipeline.query import QueryPipeline
from rag_adapter.loaders.file_loader import FileLoader
from rag_adapter.parsers.html_parser import HtmlParser
from rag_adapter.chunkers.character_chunker import CharacterChunker
from rag_adapter.retrievers.dense_retriever import DenseRetriever
from rag_adapter.fusion.rrf_fusion import RRFFusion
from rag_adapter.context.context_builder import DefaultContextBuilder
from rag_adapter.prompts.template_prompt_builder import TemplatePromptBuilder
from rag_adapter.testing.mocks import EchoEmbedder, InMemoryVectorStore, NoopReranker, EchoGenerator


async def _seed_store():
    """索引一份示範文件到 in-memory store(沿用 indexing pipeline)。"""
    store = InMemoryVectorStore()
    with tempfile.TemporaryDirectory() as tmp:
        doc = Path(tmp) / "handbook.html"
        doc.write_text(
            "<html><head><title>Onboarding</title></head><body><p>"
            + "Welcome to the team. Read the handbook carefully. " * 20
            + "</p></body></html>",
            encoding="utf-8",
        )
        indexing = IndexingPipeline(
            loader=FileLoader(loader_name="html"),
            parser=HtmlParser(),
            chunker=CharacterChunker(chunk_size=200, chunk_overlap=20),
            embedder=EchoEmbedder(),
            vector_store=store,
        )
        await indexing.index(str(doc))
    return store


async def main():
    store = await _seed_store()

    # 組裝 query pipeline:真實 retriever / fusion / context builder / prompt builder
    # + demo 用的假 embedder / reranker / generator(正式環境改用 Qwen* 與 Qdrant*)
    pipeline = QueryPipeline(
        retrievers=[DenseRetriever(EchoEmbedder(), store)],
        fusion=RRFFusion(),
        reranker=NoopReranker(),                  # 正式環境改用 QwenReranker
        context_builder=DefaultContextBuilder(max_chars=500),
        prompt_builder=TemplatePromptBuilder(),
        generator=EchoGenerator(),                # 正式環境改用 QwenGenerator
        top_k=3,
    )

    query = "Read the handbook carefully."

    # (a) 只檢索 + 組裝 context(不需 generator)
    built = await pipeline.retrieve_context(query)
    print("citations:", [c.chunk_id for c in built["citations"]])

    # (b) 生成答案(一次性)
    answer = await pipeline.answer(query)
    print("answer (前 60 字):", answer.text[:60])

    # (c) streaming(逐 token)
    tokens = [token async for token in pipeline.stream(query)]
    print("streamed tokens:", len(tokens))


if __name__ == "__main__":
    asyncio.run(main())


# --- Config 驅動(正式環境)-------------------------------------------------
# 需先:啟動 Qdrant server、建立 collection,並設定環境變數 QWEN_BASE_URL、QWEN_API_KEY。
# 要使用 answer/stream,請把 examples/rag.yaml 的 query.generation.enabled 設為 true。
#
# from rag_adapter.config import load_config
# from rag_adapter.factory import build_query_pipeline
#
# async def run_from_config(query):
#     pipeline = build_query_pipeline(load_config("examples/rag.yaml"))
#     built = await pipeline.retrieve_context(query)         # 只檢索 + context
#     # answer = await pipeline.answer(query)                # 需 generation.enabled
#     print(built["context"], built["citations"])
#
# asyncio.run(run_from_config("How do I onboard?"))
