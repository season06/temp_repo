class IndexingPipeline:
    """依序執行 load → parse → chunk → embed → upsert。各層皆為注入的 Protocol 實作。"""

    def __init__(self, loader, parser, chunker, embedder, vector_store):
        self._loader = loader
        self._parser = parser
        self._chunker = chunker
        self._embedder = embedder
        self._vector_store = vector_store

    def index(self, location):
        documents = self._loader.load(location)
        all_chunks = []
        for raw in documents:
            parsed = self._parser.parse(raw)
            all_chunks.extend(self._chunker.chunk(parsed))
        self._embedder.embed(all_chunks)
        self._vector_store.upsert(all_chunks)
        return len(all_chunks)
