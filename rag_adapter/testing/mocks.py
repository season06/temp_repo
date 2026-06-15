from rag_adapter.models import Chunk, RetrievedChunk, Citation, Answer


class PassthroughParser:
    def parse(self, document):
        return document


class PassthroughChunker:
    def chunk(self, document):
        chunk = Chunk(
            id=f"{document.id}-0",
            document_id=document.id,
            text=document.text,
            metadata=dict(document.metadata),
            source_ref=document.source_ref,
        )
        return [chunk]


class EchoEmbedder:
    """以文字長度當作 1 維向量,方便確定性測試。"""
    async def embed(self, chunks):
        for chunk in chunks:
            chunk.embedding = [float(len(chunk.text))]
        return chunks

    async def embed_query(self, text):
        return [float(len(text))]


class InMemoryVectorStore:
    def __init__(self):
        self._chunks = {}

    async def upsert(self, chunks):
        for chunk in chunks:
            self._chunks[chunk.id] = chunk

    async def delete(self, chunk_ids):
        for cid in chunk_ids:
            self._chunks.pop(cid, None)

    async def search(self, embedding, top_k):
        target = embedding[0]
        scored = []
        for chunk in self._chunks.values():
            if chunk.embedding is None:
                raise ValueError(f"chunk {chunk.id} has no embedding; embed before upsert")
            distance = abs(chunk.embedding[0] - target)
            scored.append(RetrievedChunk(chunk=chunk, score=-distance))
        scored.sort(key=lambda rc: rc.score, reverse=True)
        return scored[:top_k]


class VectorRetriever:
    """以 embedder + vector store 組成的簡單 retriever。"""
    def __init__(self, embedder, store):
        self._embedder = embedder
        self._store = store

    async def retrieve(self, query, top_k):
        embedding = await self._embedder.embed_query(query)
        return await self._store.search(embedding, top_k)


class PassthroughFusion:
    def fuse(self, ranked_lists, top_k):
        merged = [rc for ranked in ranked_lists for rc in ranked]
        merged.sort(key=lambda rc: rc.score, reverse=True)
        return merged[:top_k]


class NoopReranker:
    async def rerank(self, query, candidates, top_k):
        return candidates[:top_k]


class SimpleContextBuilder:
    def build(self, query, chunks):
        context = "\n".join(rc.chunk.text for rc in chunks)
        citations = [
            Citation(chunk_id=rc.chunk.id, source_ref=rc.chunk.source_ref)
            for rc in chunks
        ]
        return {"context": context, "citations": citations}


class TemplatePromptBuilder:
    def build_prompt(self, query, context):
        return f"Context:\n{context}\n\nQuestion: {query}"


class EchoGenerator:
    """把 prompt 前綴回去,作為確定性的假 LLM。"""
    async def generate(self, prompt, citations):
        return Answer(text=f"ANSWER: {prompt}", citations=list(citations))

    async def stream(self, prompt, citations):
        for token in prompt.split():
            yield token
