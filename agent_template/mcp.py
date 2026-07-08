from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from langchain_mcp_adapters.client import MultiServerMCPClient

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool


def load_mcp_tools(connections: dict[str, dict] | None) -> list[BaseTool]:
    """同步載入所有 MCP server 的 tools。

    connections: dict[server_name -> connection dict]，例如：
      stdio: {"transport": "stdio", "command": "python", "args": ["server.py"]}
      http:  {"transport": "streamable_http", "url": "http://host/mcp"}
    回傳 langchain BaseTool 清單;connections 為空則回傳 []。
    MCP tool 為 async-only（呼叫端需用 ainvoke）。
    注意:MCP tool 為 async-only;帶有 MCP tool 的 agent 必須以 ainvoke/astream 執行(同步 invoke 會在該 tool 上 NotImplementedError)。
    """
    if not connections:
        return []

    async def _load() -> list[BaseTool]:
        client = MultiServerMCPClient(connections)
        return await client.get_tools()

    return asyncio.run(_load())
