DEFAULT_TEMPLATE = (
    "請根據以下資料回答問題,並在適當處引用來源編號 [n]。\n\n"
    "資料:\n{context}\n\n"
    "問題:{query}"
)


class TemplatePromptBuilder:
    """以 template 把 context 與 query 組成 user prompt(system prompt 由 generator 處理)。"""

    def __init__(self, template=None):
        self._template = template or DEFAULT_TEMPLATE

    def build_prompt(self, query, context):
        return self._template.format(query=query, context=context)
