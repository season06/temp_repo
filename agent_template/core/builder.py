from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .factory import get_provider_builder
from ..config import LocalMcp, LocalSkill
from ..tools import HttpRegistryClient, load_configured_mcp_tools, skill_sources

if TYPE_CHECKING:
    from ..config import Config


class AgentBuilder:
    """累加式建構器。

    初始化時把 config 內的 skills / mcps 讀進來作為起始清單;
    add_mcp / add_skill 則是往這些清單「追加」,add_hook 追加 hook。
    最後 build() 把 mcp 載入成 tools、skill 收集成來源路徑,回傳原生 agent。
    remote 只從 config 進來:build() 依 config 各 section 的 registry_url 解析後匯流回 local。
    """

    def __init__(self, config: Config, observability: Any = None) -> None:
        self._config = config
        self._observability = observability
        # 從 config 起始(複製,避免 append 汙染 config 本身)
        self._mcps: list[LocalMcp] = list(config.mcps.local)
        self._skills: list[LocalSkill] = list(config.skills.local)
        self._hooks: list = []

    def add_mcp(self, name: str, transport: str, path: str, func: list | None = None) -> AgentBuilder:
        """追加一個 MCP server 到初始清單(來自 config 的之後)。"""
        self._mcps.append(LocalMcp(name=name, transport=transport, path=path, func=func or []))
        return self

    def add_skill(self, name: str, path: str) -> AgentBuilder:
        """追加一個本地 skill(指向含 SKILL.md 的來源路徑,交給 deepagent 原生 skills=)到初始清單。"""
        self._skills.append(LocalSkill(name=name, path=path))
        return self

    def add_hook(self, hook: Any) -> AgentBuilder:
        self._hooks.append(hook)
        return self

    def build(self) -> Any:
        """載入 tools 後委派給 factory.get_provider_builder(唯一分派點,依 config.agent.provider 選 builder)。
        注意:若掛載了 MCP,回傳的 agent 必須以 ainvoke/astream 執行(MCP tool 為 async-only)。"""
        # remote 依 config 各 section 的 registry_url 解析,append 到 local 之後(registry_url 為空則 no-op)
        registry = HttpRegistryClient()
        mcps = [*self._mcps, *registry.resolve_mcps(self._config.mcps.remote)]
        skills = [*self._skills, *registry.resolve_skills(self._config.skills.remote)]
        tools = load_configured_mcp_tools(mcps)
        return get_provider_builder(
            self._config, 
            hooks=self._hooks, 
            tools=tools,
            skills=skill_sources(skills), 
            observability=self._observability,
        )
