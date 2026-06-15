class IndexingPipeline:
    """依序執行 load → parse → chunk → embed → upsert。I/O 步驟以 await 執行。"""

    def __init__(self, loader, parser, chunker, embedder, vector_store):
        self._loader = loader
        self._parser = parser
        self._chunker = chunker
        self._embedder = embedder
        self._vector_store = vector_store

    async def index(self, location):
        documents = await self._loader.load(location)
        all_chunks = []
        for raw in documents:
            parsed = self._parser.parse(raw)
            all_chunks.extend(self._chunker.chunk(parsed))
        await self._embedder.embed(all_chunks)
        await self._vector_store.upsert(all_chunks)
        return len(all_chunks)
