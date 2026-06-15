from rag_adapter.pipeline.indexing import IndexingPipeline
from rag_adapter.loaders.file_loader import FileLoader
from rag_adapter.parsers.html_parser import HtmlParser
from rag_adapter.chunkers.character_chunker import CharacterChunker
from rag_adapter.testing.mocks import EchoEmbedder, InMemoryVectorStore


async def test_real_indexing_components_compose(tmp_path):
    page = tmp_path / "page.html"
    page.write_text(
        "<html><head><title>Doc</title></head><body><p>"
        + "word " * 50
        + "</p></body></html>",
        encoding="utf-8",
    )

    store = InMemoryVectorStore()
    pipeline = IndexingPipeline(
        loader=FileLoader(loader_name="html"),
        parser=HtmlParser(),
        chunker=CharacterChunker(chunk_size=80, chunk_overlap=10),
        embedder=EchoEmbedder(),
        vector_store=store,
    )

    count = await pipeline.index(str(page))

    assert count >= 2
    results = await store.search([80.0], top_k=1)
    assert results[0].chunk.document_id == str(page)
    assert results[0].chunk.source_ref.loader == "html"
    assert "title" in results[0].chunk.metadata
