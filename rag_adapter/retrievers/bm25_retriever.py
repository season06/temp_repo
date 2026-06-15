from rank_bm25 import BM25Okapi

from rag_adapter.models import RetrievedChunk


def _tokenize(text):
    return text.lower().split()


class BM25Retriever:
    """以 BM25 對記憶體內 chunk 語料做稀疏檢索。語料於建構時提供。

    語料如何取得(索引期收集)屬整合層的責任;此類別只負責建索引與檢索。
    """

    def __init__(self, chunks):
        self._chunks = list(chunks)
        self._bm25 = BM25Okapi([_tokenize(c.text) for c in self._chunks]) if self._chunks else None

    async def retrieve(self, query, top_k):
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(zip(self._chunks, scores), key=lambda pair: pair[1], reverse=True)
        return [RetrievedChunk(chunk=chunk, score=float(score)) for chunk, score in ranked[:top_k]]
