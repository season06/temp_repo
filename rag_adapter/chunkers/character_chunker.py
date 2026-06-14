from rag_adapter.models import Chunk


class CharacterChunker:
    """以字元數切分的重疊滑動視窗 chunker。

    日後可在同一 Chunker 介面下替換為 recursive / token-based 版本。
    """

    def __init__(self, chunk_size=800, chunk_overlap=100):
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def chunk(self, document):
        text = document.text
        step = self._chunk_size - self._chunk_overlap
        chunks = []
        index = 0
        start = 0
        while start < len(text) or index == 0:
            end = min(start + self._chunk_size, len(text))
            chunks.append(
                Chunk(
                    id=f"{document.id}#{index}",
                    document_id=document.id,
                    text=text[start:end],
                    metadata=dict(document.metadata),
                    source_ref=document.source_ref,
                    position={"index": index, "start": start, "end": end},
                )
            )
            index += 1
            if end >= len(text):
                break
            start += step
        return chunks
