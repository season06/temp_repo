"""Provider dispatch:根據 config.agent.provider 選 builder,目前僅 deepagent。"""

import os

from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

from ..config import ConfigError


def build_model(config):
    if not config.agent.model:
        raise ConfigError("config.agent.model 未設定,且 build() 也沒有提供 model")
    api_key = os.environ.get("LLM_API_KEY")
    base_url = os.environ.get("LLM_BASE_URL")
    if not api_key or not base_url:
        raise ConfigError(
            "環境變數 LLM_API_KEY / LLM_BASE_URL 未設定(可放在 config 同目錄的 .env)"
        )
    return ChatOpenAI(model=config.agent.model, api_key=api_key, base_url=base_url)


def build_deepagent(
    config, model, system_prompt, tools: list, skills: list, middleware: list, kwargs: dict
):
    if model is None:
        model = build_model(config)
    if system_prompt:
        kwargs["system_prompt"] = system_prompt
    return create_deep_agent(
        model=model, tools=tools, skills=skills, middleware=middleware, **kwargs
    )


_PROVIDERS = {"deepagent": build_deepagent}


def get_provider_builder(provider):
    if provider not in _PROVIDERS:
        supported = ", ".join(_PROVIDERS)
        raise ConfigError(f"不支援的 provider: {provider}(目前支援: {supported})")
    return _PROVIDERS[provider]
