"""範例 MCP server(stdio)。

用 FastMCP 提供幾個 tool。template 透過 stdio 以 `sys.executable local_server.py`
把它 spawn 起來(見 tools/mcp.py::mcp_to_connection),不需另外手動啟動。
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mathserver")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@mcp.tool()
def get(key: str) -> str:
    """Return a canned value for the given key."""
    return f"value-of-{key}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
