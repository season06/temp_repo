from rag_adapter.models import Document
from rag_adapter.pipeline.indexing import IndexingPipeline
from rag_adapter.testing.mocks import (
    PassthroughParser,
    PassthroughChunker,
    EchoEmbedder,
    InMemoryVectorStore,
)


class TwoDocLoader:
    async def load(self, location):
        return [
            Document(id="d1", text="aa"),
            Document(id="d2", text="aaaa"),
        ]


async def test_indexing_pipeline_indexes_documents_into_store():
    store = InMemoryVectorStore()
    pipeline = IndexingPipeline(
        loader=TwoDocLoader(),
        parser=PassthroughParser(),
        chunker=PassthroughChunker(),
        embedder=EchoEmbedder(),
        vector_store=store,
    )

    count = await pipeline.index("any-location")

    assert count == 2
    results = await store.search([4.0], top_k=1)
    assert results[0].chunk.document_id == "d2"
    assert results[0].chunk.embedding == [4.0]
