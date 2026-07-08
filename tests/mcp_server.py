from mcp.server.fastmcp import FastMCP

mcp = FastMCP("testserver")


@mcp.tool()
def echo(text: str) -> str:
    """echoes text back"""
    return "echo:" + text


if __name__ == "__main__":
    mcp.run(transport="stdio")
