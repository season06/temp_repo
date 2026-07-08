from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

from ._middleware import HookMiddleware
from .observability import ObservabilityMiddleware


def _build_llm(config):
    return ChatOpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        temperature=config.temperature,
    )


def build_agent(config, hooks=None, tools=None, observability=None):
    """建構並回傳原生 DeepAgent 物件（執行期回歸原生,無包裝）。
    hooks: Hook 清單;tools: 額外 tools;observability: 啟用時追加 ObservabilityMiddleware。"""
    llm = _build_llm(config)
    middleware = [HookMiddleware(hooks)] if hooks else []
    if observability is not None and observability.enabled:
        middleware.append(ObservabilityMiddleware(observability.instruments, observability.logger, config.model))
    return create_deep_agent(
        model=llm,
        tools=tools or [],
        system_prompt=config.system_prompt,
        middleware=middleware,
    )
