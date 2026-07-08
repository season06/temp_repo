import asyncio

from langchain_mcp_adapters.client import MultiServerMCPClient


def load_mcp_tools(connections):
    """同步載入所有 MCP server 的 tools。

    connections: dict[server_name -> connection dict]，例如：
      stdio: {"transport": "stdio", "command": "python", "args": ["server.py"]}
      http:  {"transport": "streamable_http", "url": "http://host/mcp"}
    回傳 langchain BaseTool 清單;connections 為空則回傳 []。
    MCP tool 為 async-only（呼叫端需用 ainvoke）。
    """
    if not connections:
        return []

    async def _load():
        client = MultiServerMCPClient(connections)
        return await client.get_tools()

    return asyncio.run(_load())
