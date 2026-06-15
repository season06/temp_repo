"""Indexing pipeline 快速上手範例。

兩種用法:

1) 程式組裝(本檔 main,可直接執行,無需外部服務)
   使用 in-memory 的假 embedder / vector store,適合馬上試跑、理解 pipeline 結構:

       python examples/indexing_quickstart.py

2) Config 驅動(正式環境,需 Qdrant server + Qwen API)
   見檔尾 `run_from_config` 範例,搭配 examples/rag.yaml。
"""

import asyncio
import tempfile
from pathlib import Path

from rag_adapter.pipeline.indexing import IndexingPipeline
from rag_adapter.loaders.file_loader import FileLoader
from rag_adapter.parsers.html_parser import HtmlParser
from rag_adapter.chunkers.character_chunker import CharacterChunker
from rag_adapter.testing.mocks import EchoEmbedder, InMemoryVectorStore


async def main():
    # 準備一份示範 HTML 文件
    with tempfile.TemporaryDirectory() as tmp:
        doc = Path(tmp) / "handbook.html"
        doc.write_text(
            "<html><head><title>Onboarding</title></head><body><p>"
            + "Welcome to the team. Read the handbook carefully. " * 20
            + "</p></body></html>",
            encoding="utf-8",
        )

        # 組裝 indexing pipeline:真實 loader/parser/chunker + demo 用的假 embedder/store
        pipeline = IndexingPipeline(
            loader=FileLoader(loader_name="html"),
            parser=HtmlParser(),
            chunker=CharacterChunker(chunk_size=200, chunk_overlap=20),
            embedder=EchoEmbedder(),            # 正式環境改用 QwenEmbedder
            vector_store=InMemoryVectorStore(),  # 正式環境改用 QdrantVectorStore
        )

        count = await pipeline.index(str(doc))
        print(f"indexed {count} chunks from {doc.name}")


if __name__ == "__main__":
    asyncio.run(main())


# --- Config 驅動(正式環境)-------------------------------------------------
# 需先:啟動 Qdrant server、建立 collection(維度需與 Qwen 模型一致),
#       並設定環境變數 QWEN_BASE_URL、QWEN_API_KEY。
#
# from rag_adapter.config import load_config
# from rag_adapter.factory import build_indexing_pipeline
#
# async def run_from_config(source):
#     config = load_config("examples/rag.yaml")
#     pipeline = build_indexing_pipeline(config)
#     count = await pipeline.index(source)
#     print(f"indexed {count} chunks")
#
# asyncio.run(run_from_config("./docs_to_index"))
