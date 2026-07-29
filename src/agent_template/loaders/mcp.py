"""MCP tool 載入:streamable-http only,每個 server 各自失敗各自跳過。"""

import logging
import warnings

from langchain_mcp_adapters.client import MultiServerMCPClient

from ..utils._async import run_sync

logger = logging.getLogger("agent_template")


def load_mcp_tools(servers: list, headers: dict = None) -> list:
    tools = []
    for server in servers:
        if server.transport != "streamable-http":
            warnings.warn(
                f"MCP server '{server.name}' transport '{server.transport}' 尚未支援,已跳過"
            )
            continue
        try:
            tools += run_sync(_fetch_tools(server, headers))
        except Exception as exc:
            warnings.warn(f"MCP server '{server.name}' 連線失敗,已跳過: {exc}")
    logger.info("load_mcp_tools: 載入 %d 個 mcp tool", len(tools))
    return tools


async def _fetch_tools(server, headers: dict = None):
    connection = {"transport": "streamable_http", "url": server.url}
    if headers is not None:
        connection["headers"] = headers
    client = MultiServerMCPClient({server.name: connection})
    return await client.get_tools()
