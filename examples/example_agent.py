"""示範 Agent:用 agent_template 串起 auth / MCP / skill / observability / hooks。"""

from agent_template.auth import AuthHook, HttpAuthClient
from agent_template.core import AgentBuilder


def build_example_agent(agent_config, runtime_config=None, model=None, mcp=None, skill_ids=None,
                        skill_registry=None, observability=None, auth_client=None, extra_hooks=None):
    """組出一個示範 agent 並回傳原生物件。

    agent_config: AgentConfig(LLM 設定)。runtime_config: Config(auth 端點等);
      提供時,若未注入 auth_client,會用它建預設 HttpAuthClient。
    model: 可注入自帶模型(測試/BYO)。mcp: dict[name -> connection];
    skill_ids: list[str](需搭配 skill_registry)。observability: setup_observability 的 handle;
    auth_client: 覆寫預設;extra_hooks: 額外 Hook 清單。
    """
    builder = AgentBuilder(agent_config, skill_registry=skill_registry, observability=observability, model=model)
    if auth_client is None and runtime_config is not None:
        auth_client = HttpAuthClient(runtime_config.auth_endpoint)
    if auth_client is not None:
        builder.add_hook(AuthHook(auth_client))
    for hook in (extra_hooks or []):
        builder.add_hook(hook)
    for name, connection in (mcp or {}).items():
        builder.add_mcp(name, connection)
    for skill_id in (skill_ids or []):
        builder.add_skill(skill_id)
    return builder.build()


if __name__ == "__main__":
    # 真實用法(需可用的 OpenAI-compatible 端點、auth 端點;o11y 選用):
    import asyncio

    from agent_template.config import AgentConfig, Config
    from agent_template.observability import setup_observability

    runtime = Config.from_env()
    agent_config = AgentConfig(
        api_key="sk-...", base_url="http://localhost:8000/v1", model="qwen",
        system_prompt="You are a helpful agent.",
    )
    agent = build_example_agent(
        agent_config,
        runtime_config=runtime,
        observability=setup_observability(runtime),
        mcp={"local": {"transport": "stdio", "command": "python", "args": ["my_mcp_server.py"]}},
    )
    result = asyncio.run(agent.ainvoke({"messages": [("user", "Hello!")]}))
    print(result["messages"][-1].content)
