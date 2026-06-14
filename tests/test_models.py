from rag_adapter.models import (
    SourceRef,
    Document,
    Chunk,
    RetrievedChunk,
    Citation,
    Answer,
)


def test_document_defaults():
    doc = Document(id="d1", text="hello")
    assert doc.id == "d1"
    assert doc.text == "hello"
    assert doc.metadata == {}
    assert doc.source_ref is None


def test_chunk_carries_source_ref_and_embedding():
    ref = SourceRef(loader="html", location="http://x")
    chunk = Chunk(
        id="c1",
        document_id="d1",
        text="part",
        source_ref=ref,
        embedding=[0.1, 0.2],
    )
    assert chunk.document_id == "d1"
    assert chunk.source_ref.loader == "html"
    assert chunk.embedding == [0.1, 0.2]
    assert chunk.metadata == {}


def test_retrieved_chunk_has_score():
    chunk = Chunk(id="c1", document_id="d1", text="part")
    rc = RetrievedChunk(chunk=chunk, score=0.9)
    assert rc.chunk.id == "c1"
    assert rc.score == 0.9


def test_answer_holds_citations():
    ref = SourceRef(loader="html", location="http://x")
    cit = Citation(chunk_id="c1", source_ref=ref)
    answer = Answer(text="result", citations=[cit])
    assert answer.text == "result"
    assert answer.citations[0].chunk_id == "c1"


def test_interfaces_are_importable():
    from rag_adapter import interfaces

    expected = [
        "Loader",
        "Parser",
        "Chunker",
        "Embedder",
        "VectorStore",
        "QueryTransform",
        "Retriever",
        "Fusion",
        "Reranker",
        "ContextBuilder",
        "PromptBuilder",
        "Generator",
    ]
    for name in expected:
        assert hasattr(interfaces, name), name
