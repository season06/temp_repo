from typing import Protocol, runtime_checkable

from rag_adapter.models import Document, Answer


@runtime_checkable
class Loader(Protocol):
    """取得原始 bytes / 連到資料來源,回傳尚未解析的原始 Document。"""
    def load(self, location) -> list: ...


@runtime_checkable
class Parser(Protocol):
    """從格式抽出乾淨文字與 metadata。"""
    def parse(self, document: Document) -> Document: ...


@runtime_checkable
class Chunker(Protocol):
    """把 Document 切成 Chunk。"""
    def chunk(self, document: Document) -> list: ...


@runtime_checkable
class Embedder(Protocol):
    """文字 → 向量;就地填入 chunk.embedding 並回傳。"""
    def embed(self, chunks: list) -> list: ...

    def embed_query(self, text) -> list: ...


@runtime_checkable
class VectorStore(Protocol):
    """向量寫入 / 查詢,含 upsert / delete。"""
    def upsert(self, chunks: list) -> None: ...

    def delete(self, chunk_ids: list) -> None: ...

    def search(self, embedding: list, top_k) -> list: ...


@runtime_checkable
class QueryTransform(Protocol):
    """查詢前處理(v1 僅 pass-through)。"""
    def transform(self, query) -> str: ...


@runtime_checkable
class Retriever(Protocol):
    """取回候選 RetrievedChunk。"""
    def retrieve(self, query, top_k) -> list: ...


@runtime_checkable
class Fusion(Protocol):
    """合併多路檢索結果(如 RRF)。"""
    def fuse(self, ranked_lists: list, top_k) -> list: ...


@runtime_checkable
class Reranker(Protocol):
    """重排候選。"""
    def rerank(self, query, candidates: list, top_k) -> list: ...


@runtime_checkable
class ContextBuilder(Protocol):
    """去重 / token 預算 / 組裝 context,產出 context 字串與引用。"""
    def build(self, query, chunks: list) -> dict: ...


@runtime_checkable
class PromptBuilder(Protocol):
    """以 template 把 query + context 組成 prompt。"""
    def build_prompt(self, query, context) -> str: ...


@runtime_checkable
class Generator(Protocol):
    """呼叫 LLM 生成答案。"""
    def generate(self, prompt, citations: list) -> Answer: ...

    def stream(self, prompt, citations: list): ...
