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
        self._mcp_connections[name] = connection
        return self

    def add_skill(self, skill_id):
        self._skill_ids.append(skill_id)
        return self

    def add_hook(self, hook):
        self._hooks.append(hook)
        return self

    def build(self):
        tools = list(load_mcp_tools(self._mcp_connections))
        for skill_id in self._skill_ids:
            tools.append(skill_to_tool(self._registry.get(skill_id)))
        return build_agent(self._config, hooks=self._hooks, tools=tools)
