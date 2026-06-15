from rag_adapter.loaders.file_loader import FileLoader
from rag_adapter.loaders.http_loaders import UrlLoader, TkmsLoader
from rag_adapter.parsers.html_parser import HtmlParser
from rag_adapter.parsers.structured_parsers import JsonParser, XmlParser
from rag_adapter.chunkers.character_chunker import CharacterChunker
from rag_adapter.embedders.qwen_embedder import QwenEmbedder
from rag_adapter.vectorstores.qdrant_store import QdrantVectorStore
from rag_adapter.retrievers.dense_retriever import DenseRetriever
from rag_adapter.fusion.rrf_fusion import RRFFusion
from rag_adapter.rerankers.qwen_reranker import QwenReranker
from rag_adapter.context.context_builder import DefaultContextBuilder
from rag_adapter.pipeline.indexing import IndexingPipeline
from rag_adapter.pipeline.query import QueryPipeline


def _build_loader(config):
    if config.type == "file":
        return FileLoader(loader_name=config.loader_name)
    if config.type == "url":
        return UrlLoader(loader_name=config.loader_name)
    if config.type == "tkms":
        return TkmsLoader(base_url=config.base_url)
    raise ValueError(f"unknown loader type: {config.type}")


def _build_parser(config):
    if config.type == "html":
        return HtmlParser()
    if config.type == "json":
        return JsonParser()
    if config.type == "xml":
        return XmlParser()
    raise ValueError(f"unknown parser type: {config.type}")


def _build_chunker(config):
    if config.type == "character":
        return CharacterChunker(chunk_size=config.chunk_size, chunk_overlap=config.chunk_overlap)
    raise ValueError(f"unknown chunker type: {config.type}")


def _build_embedder(config):
    if config.type == "qwen":
        return QwenEmbedder(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
            batch_size=config.batch_size,
        )
    raise ValueError(f"unknown embedder type: {config.type}")


def _build_vector_store(config):
    if config.type == "qdrant":
        from qdrant_client import AsyncQdrantClient

        return QdrantVectorStore(
            client=AsyncQdrantClient(url=config.url),
            collection=config.collection,
        )
    raise ValueError(f"unknown vector store type: {config.type}")


def build_indexing_pipeline(config):
    """依 RagConfig.indexing 組裝 IndexingPipeline。各 provider 由對應 config 區塊建立。"""
    indexing = config.indexing
    return IndexingPipeline(
        loader=_build_loader(indexing.loader),
        parser=_build_parser(indexing.parser),
        chunker=_build_chunker(indexing.chunker),
        embedder=_build_embedder(indexing.embedder),
        vector_store=_build_vector_store(indexing.vector_store),
    )


def _build_retriever(config, embedder, vector_store):
    if config.type == "dense":
        return DenseRetriever(embedder, vector_store)
    raise ValueError(f"unknown retriever type: {config.type}")


def _build_fusion(config):
    if config.type == "rrf":
        return RRFFusion(k=config.k)
    raise ValueError(f"unknown fusion type: {config.type}")


def _build_reranker(config):
    if config.type == "qwen":
        return QwenReranker(base_url=config.base_url, api_key=config.api_key, model=config.model)
    raise ValueError(f"unknown reranker type: {config.type}")


def build_query_pipeline(config):
    """依 RagConfig 組裝 QueryPipeline(到 retrieve_context 為止;生成屬 P4)。

    dense retriever 與 indexing 共用 embedder / vector store 設定。
    """
    embedder = _build_embedder(config.indexing.embedder)
    vector_store = _build_vector_store(config.indexing.vector_store)
    query = config.query
    return QueryPipeline(
        retrievers=[_build_retriever(query.retriever, embedder, vector_store)],
        fusion=_build_fusion(query.fusion),
        reranker=_build_reranker(query.reranker),
        context_builder=DefaultContextBuilder(max_chars=query.context.max_chars),
        top_k=query.top_k,
    )
