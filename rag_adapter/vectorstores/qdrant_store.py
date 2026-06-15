import uuid

from qdrant_client import models as qmodels

from rag_adapter.models import Chunk, RetrievedChunk, SourceRef


def _point_id(chunk_id):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


class QdrantVectorStore:
    """以 qdrant-client(AsyncQdrantClient)非同步儲存 / 查詢向量。

    chunk.id 以 uuid5 映成 point id,原始欄位存於 payload,search 時還原為 Chunk。
    collection 的建立與向量維度設定由呼叫端先行處理。
    """

    def __init__(self, client, collection):
        self._client = client
        self._collection = collection

    async def upsert(self, chunks):
        points = [
            qmodels.PointStruct(
                id=_point_id(chunk.id),
                vector=chunk.embedding,
                payload={
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "text": chunk.text,
                    "metadata": chunk.metadata,
                    "position": chunk.position,
                    "source_ref": self._dump_ref(chunk.source_ref),
                },
            )
            for chunk in chunks
        ]
        await self._client.upsert(collection_name=self._collection, points=points)

    async def delete(self, chunk_ids):
        await self._client.delete(
            collection_name=self._collection,
            points_selector=[_point_id(cid) for cid in chunk_ids],
        )

    async def search(self, embedding, top_k):
        hits = await self._client.search(
            collection_name=self._collection,
            query_vector=embedding,
            limit=top_k,
        )
        return [self._to_retrieved(hit) for hit in hits]

    def _to_retrieved(self, hit):
        payload = hit.payload
        chunk = Chunk(
            id=payload["chunk_id"],
            document_id=payload["document_id"],
            text=payload["text"],
            metadata=payload.get("metadata") or {},
            source_ref=self._load_ref(payload.get("source_ref")),
            position=payload.get("position") or {},
        )
        return RetrievedChunk(chunk=chunk, score=hit.score)

    def _dump_ref(self, ref):
        if ref is None:
            return None
        return {"loader": ref.loader, "location": ref.location, "position": ref.position}

    def _load_ref(self, data):
        if not data:
            return None
        return SourceRef(
            loader=data["loader"],
            location=data["location"],
            position=data.get("position") or {},
        )
