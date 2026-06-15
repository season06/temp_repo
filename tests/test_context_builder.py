from rag_adapter.models import Chunk, RetrievedChunk, SourceRef
from rag_adapter.context.context_builder import DefaultContextBuilder


def _rc(cid, text):
    ref = SourceRef(loader="file", location=f"/{cid}")
    return RetrievedChunk(chunk=Chunk(id=cid, document_id="d", text=text, source_ref=ref), score=1.0)


def test_context_builder_formats_and_cites():
    built = DefaultContextBuilder(max_chars=100).build("q", [_rc("c1", "alpha"), _rc("c2", "beta")])

    assert built["context"] == "[1] alpha\n\n[2] beta"
    assert [c.chunk_id for c in built["citations"]] == ["c1", "c2"]
    assert built["citations"][0].source_ref.location == "/c1"


def test_context_builder_dedupes():
    built = DefaultContextBuilder(max_chars=100).build("q", [_rc("c1", "alpha"), _rc("c1", "alpha")])

    assert built["context"] == "[1] alpha"
    assert len(built["citations"]) == 1


def test_context_builder_respects_budget():
    built = DefaultContextBuilder(max_chars=5).build("q", [_rc("c1", "alpha"), _rc("c2", "beta")])

    assert built["context"] == "[1] alpha"
    assert len(built["citations"]) == 1
