from rag_adapter.models import Citation


class DefaultContextBuilder:
    """依字元預算組裝 context:去重、加 [n] 來源標記、產出引用。"""

    def __init__(self, max_chars=6000):
        self._max_chars = max_chars

    def build(self, query, chunks):
        seen = set()
        parts = []
        citations = []
        used = 0
        for retrieved in chunks:
            chunk = retrieved.chunk
            if chunk.id in seen:
                continue
            seen.add(chunk.id)
            if parts and used + len(chunk.text) > self._max_chars:
                break
            parts.append(f"[{len(parts) + 1}] {chunk.text}")
            citations.append(Citation(chunk_id=chunk.id, source_ref=chunk.source_ref))
            used += len(chunk.text)
        return {"context": "\n\n".join(parts), "citations": citations}
