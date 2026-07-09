"""示範 Agent:用 agent_template 串起 auth / MCP / skill / observability / hooks。"""

from agent_template.auth import AuthHook, HttpAuthClient
from agent_template.core import AgentBuilder


def build_example_agent(config, observability=None, auth_client=None, extra_hooks=None):
    """組出一個示範 agent 並回傳原生物件。

    config: Config(llm / agent / skills / mcps / observability / auth 全都在裡面)。
      skills 與 mcps 由 AgentBuilder 直接從 config 讀取,毋須另外傳入。
    observability: setup_observability 的 handle。
    auth_client: 覆寫預設;未提供且 config.auth.endpoint 有值時,自動建 HttpAuthClient。
    extra_hooks: 額外 Hook 清單。
    """
    builder = AgentBuilder(config, observability=observability)
    if auth_client is None and config.auth.endpoint:
        auth_client = HttpAuthClient(config.auth.endpoint)
    if auth_client is not None:
        builder.add_hook(AuthHook(auth_client))
    for hook in (extra_hooks or []):
        builder.add_hook(hook)
    return builder.build()


if __name__ == "__main__":
    # 真實用法:從 config.yaml + .env 載入完整設定,再建 agent。
    import asyncio

    from agent_template.config import Config
    from agent_template.observability import setup_observability

    config = Config.load("config.yaml", ".env")
    agent = build_example_agent(
        config,
        observability=setup_observability(config.observability),
    )
    result = asyncio.run(agent.ainvoke({"messages": [("user", "Hello!")]}))
    print(result["messages"][-1].content)
