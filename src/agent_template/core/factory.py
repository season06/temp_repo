"""Provider dispatch:根據 config.agent.provider 選 builder,目前僅 deepagent。"""

import os
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_openai import ChatOpenAI

from ..config import ConfigError

_MB = 1024 * 1024
_DEFAULT_MAX_FILE_SIZE_MB = 10


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


def resolve_backend(kwargs: dict):
    """SDK 強制 FilesystemBackend + virtual_mode=True,其餘參數沿用使用者傳入的 backend。

    virtual_mode 下 root_dir 只認專案目錄(cwd)內的路徑;FilesystemBackend 建構時就把
    root_dir resolve 成絕對路徑,無從得知原字串,故改檢查解析結果有無逃出專案目錄。
    """
    backend = kwargs.pop("backend", None)
    if backend is not None and not isinstance(backend, FilesystemBackend):
        return backend  # 逃生口:其他 backend(State / Composite ...)原樣透傳
    project_dir = Path.cwd()
    root_dir, max_file_size_mb = project_dir, _DEFAULT_MAX_FILE_SIZE_MB
    if backend is not None:
        root_dir = backend.cwd
        max_file_size_mb = backend.max_file_size_bytes // _MB
        if not root_dir.is_relative_to(project_dir):
            raise ConfigError(
                f"backend 的 root_dir 只能是專案目錄({project_dir})內的相對路徑,"
                f"目前指向 {root_dir}"
            )
    return FilesystemBackend(
        root_dir=root_dir, virtual_mode=True, max_file_size_mb=max_file_size_mb
    )


def build_deepagent(
    config, model, system_prompt, tools: list, skills: list, middleware: list, kwargs: dict
):
    if model is None:
        model = build_model(config)
    if system_prompt:
        kwargs["system_prompt"] = system_prompt
    backend = resolve_backend(kwargs)  # 先 pop 掉 kwargs 裡的 backend,才不會重複傳參
    return create_deep_agent(
        model=model, tools=tools, skills=skills, middleware=middleware, backend=backend, **kwargs
    )


_PROVIDERS = {"deepagent": build_deepagent}


def get_provider_builder(provider):
    if provider not in _PROVIDERS:
        supported = ", ".join(_PROVIDERS)
        raise ConfigError(f"不支援的 provider: {provider}(目前支援: {supported})")
    return _PROVIDERS[provider]
