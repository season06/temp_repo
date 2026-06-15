import uuid

from rag_adapter.models import Chunk, SourceRef
from rag_adapter.vectorstores.qdrant_store import QdrantVectorStore


class FakeHit:
    def __init__(self, payload, score):
        self.payload = payload
        self.score = score


class FakeQdrantClient:
    def __init__(self, hits=None):
        self.upserted = None
        self.deleted = None
        self.search_args = None
        self._hits = hits or []

    async def upsert(self, collection_name, points):
        self.upserted = {"collection": collection_name, "points": points}

    async def delete(self, collection_name, points_selector):
        self.deleted = {"collection": collection_name, "selector": points_selector}

    async def search(self, collection_name, query_vector, limit):
        self.search_args = {
            "collection": collection_name,
            "query_vector": query_vector,
            "limit": limit,
        }
        return self._hits


def _expected_point_id(chunk_id):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


async def test_upsert_maps_chunk_to_point_with_payload():
    client = FakeQdrantClient()
    store = QdrantVectorStore(client=client, collection="docs")
    chunk = Chunk(
        id="c1",
        document_id="d1",
        text="hello",
        metadata={"title": "T"},
        source_ref=SourceRef(loader="url", location="http://x"),
        embedding=[0.1, 0.2],
        position={"index": 0, "start": 0, "end": 5},
    )

    await store.upsert([chunk])

    point = client.upserted["points"][0]
    assert client.upserted["collection"] == "docs"
    assert point.id == _expected_point_id("c1")
    assert point.vector == [0.1, 0.2]
    assert point.payload["chunk_id"] == "c1"
    assert point.payload["text"] == "hello"
    assert point.payload["source_ref"] == {
        "loader": "url",
        "location": "http://x",
        "position": {},
    }


async def test_delete_maps_ids():
    client = FakeQdrantClient()
    store = QdrantVectorStore(client=client, collection="docs")

    await store.delete(["c1"])

    assert client.deleted["selector"] == [_expected_point_id("c1")]


async def test_search_reconstructs_retrieved_chunks():
    payload = {
        "chunk_id": "c1",
        "document_id": "d1",
        "text": "hello",
        "metadata": {"title": "T"},
        "position": {"index": 0, "start": 0, "end": 5},
        "source_ref": {"loader": "url", "location": "http://x", "position": {}},
    }
    client = FakeQdrantClient(hits=[FakeHit(payload, score=0.87)])
    store = QdrantVectorStore(client=client, collection="docs")

    results = await store.search([0.1, 0.2], top_k=3)

    assert client.search_args["limit"] == 3
    assert results[0].score == 0.87
    assert results[0].chunk.id == "c1"
    assert results[0].chunk.text == "hello"
    assert results[0].chunk.source_ref.loader == "url"
