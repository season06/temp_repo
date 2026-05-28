from mcp.server.fastmcp import FastMCP
import httpx
import os
from datetime import datetime, timedelta, timezone

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
mcp = FastMCP("promql", host="0.0.0.0", port=5001, stateless_http=True)


async def _do_instant_query(
    expr: str, time: str = None, prometheus_url: str = None
) -> dict:
    url = prometheus_url or PROMETHEUS_URL
    params = {"query": expr}
    if time:
        params["time"] = time
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{url}/api/v1/query", params=params)
        resp.raise_for_status()
        data = resp.json()
    if data["status"] != "success":
        raise RuntimeError(f"Prometheus error: {data.get('error', data['status'])}")
    return {"status": data["status"], "result": data["data"]["result"]}


async def _do_range_query(
    expr: str,
    start: str,
    end: str = None,
    duration_minutes: int = 30,
    step: str = "1m",
    prometheus_url: str = None,
) -> dict:
    url = prometheus_url or PROMETHEUS_URL
    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        start_ts = start_dt.timestamp()
    except (ValueError, AttributeError):
        start_ts = float(start)
        start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)

    if end:
        try:
            end_ts = datetime.fromisoformat(end.replace("Z", "+00:00")).timestamp()
        except (ValueError, AttributeError):
            end_ts = float(end)
    else:
        end_ts = (start_dt + timedelta(minutes=duration_minutes)).timestamp()

    params = {"query": expr, "start": start_ts, "end": end_ts, "step": step}
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{url}/api/v1/query_range", params=params)
        resp.raise_for_status()
        data = resp.json()
    if data["status"] != "success":
        raise RuntimeError(f"Prometheus error: {data.get('error', data['status'])}")
    return {"status": data["status"], "result": data["data"]["result"]}


@mcp.tool()
async def promql_query(expr: str, time: str = None) -> dict:
    """Execute an instant PromQL query. Returns current metric values."""
    return await _do_instant_query(expr, time)


@mcp.tool()
async def promql_query_range(
    expr: str,
    start: str,
    end: str = None,
    duration_minutes: int = 30,
    step: str = "1m",
) -> dict:
    """Execute a range PromQL query. start accepts ISO 8601 or Unix timestamp."""
    return await _do_range_query(expr, start, end, duration_minutes, step)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
