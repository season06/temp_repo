"""示範 Agent:用 agent_template 串起(強制)auth / MCP / skill / observability / hooks。"""

from agent_template.core import AgentBuilder


def build_example_agent(config, observability=None, extra_hooks=None):
    """組出一個示範 agent 並回傳原生物件。

    auth 由 SDK 於 build 時強制注入(入口 + per-tool),使用者無法移除;
    只需在 config.auth.endpoint 設好端點即可。呼叫時以 context={"identity": ...} 傳入身分。
    extra_hooks: 額外的商業邏輯 Hook,會疊加在強制 auth 之後執行。
    """
    builder = AgentBuilder(config, observability=observability)
    for hook in (extra_hooks or []):
        builder.add_hook(hook)
    return builder.build()


if __name__ == "__main__":
    import asyncio

    from agent_template.config import Config
    from agent_template.observability import setup_observability

    config = Config.load("config.yaml", ".env")   # .env 需含 AUTH_ENDPOINT
    agent = build_example_agent(config, observability=setup_observability(config.observability))
    result = asyncio.run(agent.ainvoke(
        {"messages": [("user", "Hello!")]},
        context={"identity": "demo-user"},
    ))
    print(result["messages"][-1].content)
