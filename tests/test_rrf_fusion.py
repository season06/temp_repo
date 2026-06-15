from rag_adapter.models import Chunk, RetrievedChunk
from rag_adapter.fusion.rrf_fusion import RRFFusion


def _rc(cid):
    return RetrievedChunk(chunk=Chunk(id=cid, document_id="d", text=cid), score=0.0)


def test_rrf_fusion_merges_and_ranks():
    list1 = [_rc("c1"), _rc("c2"), _rc("c3")]
    list2 = [_rc("c2"), _rc("c3")]

    fused = RRFFusion(k=60).fuse([list1, list2], top_k=3)

    assert [rc.chunk.id for rc in fused] == ["c2", "c3", "c1"]
    assert fused[0].score > fused[1].score > fused[2].score


def test_rrf_fusion_dedupes_by_chunk_id():
    fused = RRFFusion().fuse([[_rc("c1")], [_rc("c1")]], top_k=5)

    assert len(fused) == 1
    assert fused[0].chunk.id == "c1"
