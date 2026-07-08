from .factory import build_agent
from .mcp import load_mcp_tools
from .skills import MockSkillRegistry, skill_to_tool


class AgentBuilder:
    """累加式建構器:add_mcp / add_skill / add_hook,最後 build() 回傳原生 agent。"""

    def __init__(self, config, skill_registry=None):
        self._config = config
        self._registry = skill_registry or MockSkillRegistry()
        self._mcp_connections = {}
        self._skill_ids = []
        self._hooks = []

    def add_mcp(self, name, connection):
        """以 name 為鍵;同名重複呼叫會覆蓋(取最後一次),不同 name 則累加多個 server。"""
        self._mcp_connections[name] = connection
        return self

    def add_skill(self, skill_id):
        self._skill_ids.append(skill_id)
        return self

    def add_hook(self, hook):
        self._hooks.append(hook)
        return self

    def build(self):
        """注意:若掛載了 MCP,回傳的 agent 必須以 ainvoke/astream 執行(MCP tool 為 async-only)。"""
        tools = list(load_mcp_tools(self._mcp_connections))
        for skill_id in self._skill_ids:
            tools.append(skill_to_tool(self._registry.get(skill_id)))
        return build_agent(self._config, hooks=self._hooks, tools=tools)
