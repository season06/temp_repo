from rag_adapter.models import Chunk
from rag_adapter.retrievers.bm25_retriever import BM25Retriever


async def test_bm25_retriever_ranks_by_term_overlap():
    chunks = [
        Chunk(id="c1", document_id="d", text="the cat sat on the mat"),
        Chunk(id="c2", document_id="d", text="dogs run in the park"),
        Chunk(id="c3", document_id="d", text="a cat and a dog"),
    ]
    retriever = BM25Retriever(chunks)

    results = await retriever.retrieve("cat", top_k=2)

    ids = [rc.chunk.id for rc in results]
    assert "c1" in ids or "c3" in ids
    assert results[0].score >= results[1].score


async def test_bm25_retriever_empty_corpus():
    retriever = BM25Retriever([])

    assert await retriever.retrieve("anything", top_k=5) == []
