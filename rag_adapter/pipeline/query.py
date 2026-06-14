class QueryPipeline:
    """依序執行 (transform?) → retrieve(多路) → fuse → rerank → build context
    → build prompt → generate。各層皆為注入的 Protocol 實作。

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

    def _prepare(self, query):
        if self._query_transform is not None:
            query = self._query_transform.transform(query)
        ranked_lists = [r.retrieve(query, self._top_k) for r in self._retrievers]
        fused = self._fusion.fuse(ranked_lists, self._top_k)
        reranked = self._reranker.rerank(query, fused, self._top_k)
        built = self._context_builder.build(query, reranked)
        prompt = self._prompt_builder.build_prompt(query, built["context"])
        return prompt, built["citations"]

    def answer(self, query):
        prompt, citations = self._prepare(query)
        return self._generator.generate(prompt, citations)

    def stream(self, query):
        prompt, citations = self._prepare(query)
        return self._generator.stream(prompt, citations)
