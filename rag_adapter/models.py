from dataclasses import dataclass, field


@dataclass
class SourceRef:
    """指回原始來源,供引用與可追溯使用。"""
    loader: str
    location: str
    position: dict = field(default_factory=dict)


@dataclass
class Document:
    """Loader/Parser 產出的整份文件。"""
    id: str
    text: str
    metadata: dict = field(default_factory=dict)
    source_ref: SourceRef = None


@dataclass
class Chunk:
    """Chunker 切出的片段,貫穿 embedding/retrieval/context。"""
    id: str
    document_id: str
    text: str
    metadata: dict = field(default_factory=dict)
    source_ref: SourceRef = None
    embedding: list = None
    position: dict = field(default_factory=dict)


@dataclass
class RetrievedChunk:
    """檢索/重排後帶分數的片段。"""
    chunk: Chunk
    score: float


@dataclass
class Citation:
    """ContextBuilder/Generator 產出的引用。"""
    chunk_id: str
    source_ref: SourceRef


@dataclass
class Answer:
    """Generator 的最終輸出。"""
    text: str
    citations: list = field(default_factory=list)
