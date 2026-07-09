from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

from ..hooks import HookMiddleware
from ..observability import ObservabilityMiddleware

if TYPE_CHECKING:
    from ..config import Config, LLMConfig


# ===================
#     DeepAgent
# ===================


def _build_llm(llm: LLMConfig) -> Any:
    return ChatOpenAI(
        api_key=llm.api_key,
        base_url=llm.base_url,
        model=llm.model,
        temperature=llm.temperature,
    )


def build_deepagent(config: Config, hooks: list | None = None, tools: list | None = None, observability: Any = None) -> Any:
    """deepagent provider:由 config.llm 建 ChatOpenAI,建構並回傳原生 DeepAgent 物件（執行期回歸原生,無包裝）。"""
    llm = _build_llm(config.llm)
    middleware = [HookMiddleware(hooks)] if hooks else []
    if observability is not None and observability.enabled:
        middleware.append(ObservabilityMiddleware(observability.instruments, observability.logger, config.llm.model))
    return create_deep_agent(
        model=llm,
        tools=tools or [],
        system_prompt=config.agent.system_prompt,
        middleware=middleware,
    )


# =========================
#   Provider dispatch
# =========================


# provider 名稱 -> 具體 build 函式。新框架的 adapter 用 register_provider 註冊即可被 config.agent.provider 選用。
_PROVIDER_BUILDERS: dict[str, Callable] = {
    "deepagent": build_deepagent,
}


def register_provider(name: str, builder: Callable) -> None:
    """註冊(或覆寫)一個 provider 的 build 函式,簽章需與 build_deepagent 相同。"""
    _PROVIDER_BUILDERS[name] = builder


def get_provider_builder(config: Config, hooks: list | None = None, tools: list | None = None, observability: Any = None) -> Any:
    """唯一入口:依 config.agent.provider 選出具體 provider 的 build 函式並執行,回傳原生 agent。
    未知 provider 拋出清楚錯誤。AgentBuilder.build 與外部呼叫者都經由此,避免重複分派邏輯。"""
    provider = config.agent.provider
    try:
        builder = _PROVIDER_BUILDERS[provider]
    except KeyError:
        raise ValueError(
            f"unsupported provider: {provider!r}; supported: {sorted(_PROVIDER_BUILDERS)}"
        ) from None
    return builder(config, hooks=hooks, tools=tools, observability=observability)
