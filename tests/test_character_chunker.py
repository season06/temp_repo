import pytest

from rag_adapter.models import Document, SourceRef
from rag_adapter.chunkers.character_chunker import CharacterChunker


def test_character_chunker_splits_with_overlap():
    doc = Document(
        id="d1",
        text="abcdefghij",
        source_ref=SourceRef(loader="file", location="/p"),
    )
    chunks = CharacterChunker(chunk_size=4, chunk_overlap=1).chunk(doc)

    assert [c.text for c in chunks] == ["abcd", "defg", "ghij"]
    assert chunks[0].id == "d1#0"
    assert chunks[1].id == "d1#1"
    assert chunks[1].document_id == "d1"
    assert chunks[1].position == {"index": 1, "start": 3, "end": 7}
    assert chunks[0].source_ref.location == "/p"


def test_character_chunker_short_text_single_chunk():
    doc = Document(id="d2", text="hi")
    chunks = CharacterChunker(chunk_size=100, chunk_overlap=10).chunk(doc)

    assert len(chunks) == 1
    assert chunks[0].text == "hi"


def test_character_chunker_rejects_bad_overlap():
    with pytest.raises(ValueError):
        CharacterChunker(chunk_size=10, chunk_overlap=10)
