from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

from langchain_mcp_adapters.client import MultiServerMCPClient

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from ..config import LocalMcp


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


def mcp_to_connection(mcp: LocalMcp) -> dict:
    """把 config 的 LocalMcp(name/transport/path/func)翻譯成 langchain-mcp-adapters 的 connection dict。

    - stdio:           path 視為要執行的 .py → {command: <python>, args: [path]}
    - streamable_http/sse: path 視為 URL      → {url: path}
    """
    if mcp.transport == "stdio":
        return {"transport": "stdio", "command": sys.executable, "args": [mcp.path]}
    return {"transport": mcp.transport, "url": mcp.path}


def load_configured_mcp_tools(mcps: list[LocalMcp]) -> list[BaseTool]:
    """從 config 的 LocalMcp 清單載入 tools;若某 server 指定了 func,只保留該清單內的 tool。

    逐 server 載入以保留 per-server 的 func 過濾語意(空清單 = 全載)。
    """
    tools: list[BaseTool] = []
    for mcp in mcps:
        loaded = load_mcp_tools({mcp.name: mcp_to_connection(mcp)})
        if mcp.func:
            loaded = [t for t in loaded if t.name in mcp.func]
        tools.extend(loaded)
    return tools
