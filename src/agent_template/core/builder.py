"""AgentBuilder:init 階段 merge 各來源,build() 套衝突規則後回傳 Agent。

優先序一條鏈:remote > local config > build(),撞名高層贏,且一定發 warning。
"""

import logging
import warnings
from pathlib import Path

from ..a2a.card import resolve_card
from ..config import load_config
from ..loaders.a2a import load_a2a_tools
from ..loaders.mcp import load_mcp_tools
from ..loaders.registry import fetch_remote, remote_mcp_headers
from ..loaders.skills import scan_skills
from ..loaders.tools import scan_tools
from .agent import Agent
from .factory import get_provider_builder

logger = logging.getLogger("agent_template")

# SDK 必要 middleware,建 agent 時一律掛上(具體項目待定,先留空)
_SDK_MIDDLEWARE = []


class AgentBuilder:
    def __init__(self, config):
        if not isinstance(config, (str, Path)):
            raise TypeError("AgentBuilder 只接受 config 檔路徑 (str 或 Path)")
        self._config = load_config(config)
        remote = fetch_remote(self._config.agent.name)
        remote_tools, remote_skills = [], []
        if remote:
            # agent 區塊整包以 remote 為準;name 是查詢 key,永遠取 local
            self._config.agent = remote.config.agent.model_copy(
                update={"name": self._config.agent.name}
            )
            logger.info("使用 remote 設定建立 agent '%s'", self._config.agent.name)
            headers = remote_mcp_headers()
            if remote.config.mcp and headers is None:
                warnings.warn("remote mcp 需要 AUTH_TOKEN 但未設定,可能驗證失敗")
            remote_tools = load_mcp_tools(remote.config.mcp, headers=headers)
            if remote.skills_dir:
                remote_skills = scan_skills([remote.skills_dir])
        # remote 排前面:dedupe 先到先贏 = remote > local;a2a 排 local 來源之後
        self._tools = _dedupe_named([
            *remote_tools,
            *scan_tools(self._config.local_tools),
            *load_mcp_tools(self._config.local_mcp),
            *load_a2a_tools(self._config.local_a2a),
        ], kind="tool")
        self._skills = _dedupe_skills([*remote_skills, *scan_skills(self._config.local_skills)])
        self._card = resolve_card(
            self._config.agent_card, remote.card_path if remote else None
        )

    def build(self, **kwargs):
        model = self._resolve_model(kwargs)
        system_prompt = self._resolve_scalar("system_prompt", kwargs)
        tools = _merge_named(self._tools, kwargs.pop("tools", None) or [], kind="tool")
        skills = _merge_skills(self._skills, kwargs.pop("skills", None) or [])
        middleware = _merge_middlewares(_SDK_MIDDLEWARE, kwargs.pop("middleware", None) or [])
        build_native = get_provider_builder(self._config.agent.provider)
        native = build_native(self._config, model, system_prompt, tools, skills, middleware, kwargs)
        return Agent(native, card=self._card)

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


def _dedupe_named(items: list, kind) -> list:
    result, names = [], set()
    for item in items:
        if item.name in names:
            warnings.warn(f'{kind} "{item.name}" 來源間重複,保留優先來源(remote > local)')
            continue
        result.append(item)
        names.add(item.name)
    return result


def _dedupe_skills(paths: list) -> list:
    result, names = [], set()
    for p in paths:
        name = Path(p).name
        if name in names:
            warnings.warn(f'skill "{name}" 來源間重複,保留優先來源(remote > local)')
            continue
        result.append(str(p))
        names.add(name)
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
