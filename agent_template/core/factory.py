from __future__ import annotations

from typing import TYPE_CHECKING, Any

from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

from ..hooks import HookMiddleware
from ..observability import ObservabilityMiddleware

if TYPE_CHECKING:
    from ..config import AgentConfig


def _build_llm(config: AgentConfig) -> Any:
    return ChatOpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        temperature=config.temperature,
    )


def build_agent(config: AgentConfig, hooks: list | None = None, tools: list | None = None, observability: Any = None, model: Any = None) -> Any:
    """建構並回傳原生 DeepAgent 物件（執行期回歸原生,無包裝）。
    model: 若提供則直接使用(自帶已設定模型),否則由 config 建 ChatOpenAI。"""
    llm = model if model is not None else _build_llm(config)
    middleware = [HookMiddleware(hooks)] if hooks else []
    if observability is not None and observability.enabled:
        middleware.append(ObservabilityMiddleware(observability.instruments, observability.logger, config.model))
    return create_deep_agent(
        model=llm,
        tools=tools or [],
        system_prompt=config.system_prompt,
        middleware=middleware,
    )
