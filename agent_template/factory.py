from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

from ._middleware import HookMiddleware


def _build_llm(config):
    return ChatOpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        temperature=config.temperature,
    )


def build_agent(config, hooks=None):
    """建構並回傳原生 DeepAgent 物件（執行期回歸原生,無包裝）。
    hooks: Hook 清單;於建構期翻譯成 middleware 注入。"""
    llm = _build_llm(config)
    middleware = [HookMiddleware(hooks)] if hooks else []
    return create_deep_agent(
        model=llm,
        tools=[],
        system_prompt=config.system_prompt,
        middleware=middleware,
    )
