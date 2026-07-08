"""示範 Agent:用 agent_template 串起 auth / MCP / skill / observability / hooks。"""

from agent_template.auth import AuthHook, HttpAuthClient
from agent_template.builder import AgentBuilder


def build_example_agent(config, model=None, mcp=None, skill_ids=None, skill_registry=None,
                        observability=None, auth_client=None, extra_hooks=None):
    """組出一個示範 agent 並回傳原生物件。

    config: AgentConfig。model: 可注入自帶模型(測試/BYO)。
    mcp: dict[name -> connection];skill_ids: list[str](需搭配 skill_registry)。
    observability: setup_observability 的 handle;auth_client: 覆寫預設 HttpAuthClient。
    extra_hooks: 額外的 Hook 清單。
    """
    builder = AgentBuilder(config, skill_registry=skill_registry, observability=observability, model=model)
    builder.add_hook(AuthHook(auth_client if auth_client is not None else HttpAuthClient(config.auth_endpoint)))
    for hook in (extra_hooks or []):
        builder.add_hook(hook)
    for name, connection in (mcp or {}).items():
        builder.add_mcp(name, connection)
    for skill_id in (skill_ids or []):
        builder.add_skill(skill_id)
    return builder.build()


if __name__ == "__main__":
    # 真實用法(需可用的 OpenAI-compatible 端點、auth 端點;o11y 選用):
    from agent_template.config import AgentConfig, Config
    from agent_template.observability import setup_observability

    runtime = Config.from_env()
    agent_config = AgentConfig(
        api_key="sk-...", base_url="http://localhost:8000/v1", model="qwen",
        system_prompt="You are a helpful agent.",
    )
    agent = build_example_agent(
        agent_config,
        observability=setup_observability(runtime),
        mcp={"local": {"transport": "stdio", "command": "python", "args": ["my_mcp_server.py"]}},
    )
    result = agent.invoke({"messages": [("user", "Hello!")]})
    print(result["messages"][-1].content)
