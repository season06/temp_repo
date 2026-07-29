"""AgentBuilder:init 階段 merge 三種來源,build() 套衝突規則後回傳 Agent。

衝突規則一句話:衝突時 config 贏,且一定發 warning。
"""

import warnings
from pathlib import Path

from ..config import load_config
from ..loaders.mcp import load_mcp_tools
from ..loaders.skills import scan_skills
from ..loaders.tools import scan_tools
from .agent import Agent
from .factory import get_provider_builder


# SDK 必要 middleware,建 agent 時一律掛上(具體項目待定,先留空)
_SDK_MIDDLEWARE = []


class AgentBuilder:
    def __init__(self, config):
        if not isinstance(config, (str, Path)):
            raise TypeError("AgentBuilder 只接受 config 檔路徑 (str 或 Path)")
        self._config = load_config(config)
        self._tools = _dedupe_config_tools([
            *scan_tools(self._config.local_tools),
            *load_mcp_tools(self._config.local_mcp),
        ])
        self._skills = scan_skills(self._config.local_skills)

    def build(self, **kwargs):
        model = self._resolve_model(kwargs)
        system_prompt = self._resolve_scalar("system_prompt", kwargs)
        tools = _merge_named(self._tools, kwargs.pop("tools", None) or [], kind="tool")
        skills = _merge_skills(self._skills, kwargs.pop("skills", None) or [])
        middleware = _merge_middlewares(_SDK_MIDDLEWARE, kwargs.pop("middleware", None) or [])
        build_native = get_provider_builder(self._config.agent.provider)
        native = build_native(self._config, model, system_prompt, tools, skills, middleware, kwargs)
        return Agent(native)

    def _resolve_model(self, kwargs: dict):
        provided = kwargs.pop("model", None)
        if self._config.agent.model and provided is not None:
            warnings.warn("config 與 build() 同時提供 model,以 config 為主")
            return None
        return provided  # None 時 factory 會依 config 建 model

    def _resolve_scalar(self, name, kwargs: dict):
        config_value = getattr(self._config.agent, name)
        provided = kwargs.pop(name, None)
        if config_value and provided is not None:
            warnings.warn(f"config 與 build() 同時提供 {name},以 config 為主")
            return config_value
        return config_value or provided


def _dedupe_config_tools(tools: list) -> list:
    result, names = [], set()
    for t in tools:
        if t.name in names:
            warnings.warn(f'config 來源中 tool "{t.name}" 重複,保留先載入者')
            continue
        result.append(t)
        names.add(t.name)
    return result


def _merge_named(config_items: list, build_items: list, kind) -> list:
    merged = list(config_items)
    names = {item.name for item in merged}
    for item in build_items:
        if item.name in names:
            warnings.warn(f'{kind} "{item.name}" 在 config 與 build() 撞名,保留 config、丟棄 build()')
            continue
        merged.append(item)
        names.add(item.name)
    return merged


def _merge_middlewares(sdk_items: list, build_items: list) -> list:
    return [*sdk_items, *build_items]  # SDK 必要的在前,使用者的在後,不可移除 SDK 那組


def _merge_skills(config_paths: list, build_paths: list) -> list:
    merged = list(config_paths)
    names = {Path(p).name for p in merged}
    for p in build_paths:
        name = Path(p).name
        if name in names:
            warnings.warn(f'skill "{name}" 在 config 與 build() 撞名,保留 config、丟棄 build()')
            continue
        merged.append(str(p))
        names.add(name)
    return merged
