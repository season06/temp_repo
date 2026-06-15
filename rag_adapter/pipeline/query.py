class QueryPipeline:
    """依序執行 (transform?) → retrieve(多路) → fuse → rerank → build context
    → build prompt → generate。I/O 步驟以 await 執行;stream 為 async generator。

    query_transform 為可選;傳入 None 時跳過。
    """

    def __init__(
        self,
        retrievers,
        fusion,
        reranker,
        context_builder,
        prompt_builder,
        generator,
        top_k,
        query_transform=None,
    ):
        self._retrievers = retrievers
        self._fusion = fusion
        self._reranker = reranker
        self._context_builder = context_builder
        self._prompt_builder = prompt_builder
        self._generator = generator
        self._top_k = top_k
        self._query_transform = query_transform

    async def _prepare(self, query):
        if self._query_transform is not None:
            query = self._query_transform.transform(query)
        ranked_lists = []
        for retriever in self._retrievers:
            ranked_lists.append(await retriever.retrieve(query, self._top_k))
        fused = self._fusion.fuse(ranked_lists, self._top_k)
        reranked = await self._reranker.rerank(query, fused, self._top_k)
        built = self._context_builder.build(query, reranked)
        prompt = self._prompt_builder.build_prompt(query, built["context"])
        return prompt, built["citations"]

    async def answer(self, query):
        prompt, citations = await self._prepare(query)
        return await self._generator.generate(prompt, citations)

    async def stream(self, query):
        prompt, citations = await self._prepare(query)
        async for token in self._generator.stream(prompt, citations):
            yield token
