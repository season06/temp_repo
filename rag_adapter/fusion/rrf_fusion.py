from rag_adapter.models import RetrievedChunk


class RRFFusion:
    """Reciprocal Rank Fusion:合併多路排序,score = Σ 1/(k + rank)(rank 自 1 起算)。"""

    def __init__(self, k=60):
        self._k = k

    def fuse(self, ranked_lists, top_k):
        scores = {}
        chunks = {}
        for ranked in ranked_lists:
            for rank, retrieved in enumerate(ranked):
                cid = retrieved.chunk.id
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (self._k + rank + 1)
                if cid not in chunks:
                    chunks[cid] = retrieved.chunk
        fused = [RetrievedChunk(chunk=chunks[cid], score=score) for cid, score in scores.items()]
        fused.sort(key=lambda rc: rc.score, reverse=True)
        return fused[:top_k]
