class QueryPipeline:
    """依序執行 (transform?) → retrieve(多路) → fuse → rerank → build context
    →(可選)build prompt → generate。I/O 步驟以 await 執行。

    retrieve_context() 只跑到組裝 context(產出 context + 引用),不需 generator。
    answer()/stream() 需要 prompt_builder 與 generator(P4 才接);未提供時呼叫會報錯。
    """

    def __init__(
        self,
        retrievers,
        fusion,
        reranker,
        context_builder,
        top_k,
        prompt_builder=None,
        generator=None,
        query_transform=None,
    ):
        self._retrievers = retrievers
        self._fusion = fusion
        self._reranker = reranker
        self._context_builder = context_builder
        self._top_k = top_k
        self._prompt_builder = prompt_builder
        self._generator = generator
        self._query_transform = query_transform

    async def _retrieve(self, query):
        if self._query_transform is not None:
            query = self._query_transform.transform(query)
        ranked_lists = []
        for retriever in self._retrievers:
            ranked_lists.append(await retriever.retrieve(query, self._top_k))
        fused = self._fusion.fuse(ranked_lists, self._top_k)
        reranked = await self._reranker.rerank(query, fused, self._top_k)
        return query, reranked

    async def retrieve(self, query):
        _, reranked = await self._retrieve(query)
        return reranked

    async def retrieve_context(self, query):
        prepared_query, reranked = await self._retrieve(query)
        return self._context_builder.build(prepared_query, reranked)

    async def _prepare(self, query):
        built = await self.retrieve_context(query)
        if self._prompt_builder is None or self._generator is None:
            raise RuntimeError("prompt_builder and generator are required for answer()/stream()")
        prompt = self._prompt_builder.build_prompt(query, built["context"])
        return prompt, built["citations"]

    async def answer(self, query):
        prompt, citations = await self._prepare(query)
        return await self._generator.generate(prompt, citations)

    async def stream(self, query):
        prompt, citations = await self._prepare(query)
        async for token in self._generator.stream(prompt, citations):
            yield token
