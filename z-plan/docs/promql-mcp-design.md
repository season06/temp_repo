# PromQL MCP Integration for auto_alert_recovery

**Date:** 2026-05-28  
**Status:** Approved

## Summary

Add a PromQL MCP server to the `auto_alert_recovery` workflow so the investigation step has access to live Prometheus metric data. Also provision a local Prometheus + node_exporter stack for end-to-end validation.

---

## Architecture

```
analyze_alert_ref
       ├─ doc_search_ref        (LLM_SEARCH_INDEX, optional:true)  ← existing
       └─ query_prometheus_ref  (CALL_MCP_TOOL, optional:true)     ← new
               ↓
       join_prometheus_ref  (JOIN)                                  ← new
               ↓
       investigation_ref    (LLM_CHAT_COMPLETE)                    ← updated prompt
               ↓
       ... (rest of workflow unchanged)
```

---

## Section 1 — Workflow Changes (`auto_alert_recovery_workflow.json`)

### New task: `query_prometheus`

Inserted after `analyze_alert`, parallel to `doc_search`.

```json
{
  "name": "query_prometheus",
  "taskReferenceName": "query_prometheus_ref",
  "type": "CALL_MCP_TOOL",
  "optional": true,
  "inputParameters": {
    "mcpServer": "${workflow.input.prometheus_mcp_url}",
    "method": "promql_query_range",
    "expr": "${alert_ingestion_ref.output.result.promql}",
    "start": "${alert_ingestion_ref.output.result.startsAt}",
    "duration_minutes": 30
  }
}
```

### New task: `join_prometheus`

Merges `doc_search_ref` and `query_prometheus_ref` before investigation.

```json
{
  "name": "join_prometheus",
  "taskReferenceName": "join_prometheus_ref",
  "type": "JOIN",
  "joinOn": ["doc_search_ref", "query_prometheus_ref"]
}
```

### Updated task: `investigation`

Prompt gains a third context block:

```
Prometheus Metric Data: ${query_prometheus_ref.output.content}
```

If `query_prometheus_ref` is skipped (optional), the field resolves to empty string — the LLM ignores it gracefully.

### New workflow input parameter

```
"prometheus_mcp_url"   (optional, default "http://localhost:5001/mcp")
```

---

## Section 2 — PromQL MCP Server

**Location:** `z-plan/promql-mcp/`

### Files

```
z-plan/promql-mcp/
├── server.py
├── requirements.txt
└── Dockerfile
```

### Tools exposed

| Tool | Prometheus API | Purpose |
|------|---------------|---------|
| `promql_query` | `GET /api/v1/query` | Instant query — current value |
| `promql_query_range` | `GET /api/v1/query_range` | Range query — 30-min trend (default, step 1m) |

### `server.py` structure

```python
from mcp.server.fastmcp import FastMCP
import httpx, os, datetime

mcp = FastMCP("promql")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")

@mcp.tool()
async def promql_query(expr: str, time: str = None) -> dict:
    """Execute an instant PromQL query. Returns current metric values."""
    ...

@mcp.tool()
async def promql_query_range(
    expr: str,
    start: str,
    end: str = None,
    duration_minutes: int = 30,
    step: str = "1m"
) -> dict:
    """Execute a range PromQL query. start accepts ISO timestamp or Unix timestamp."""
    ...

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=5001)
```

### Parameter details

- `start`: accepts ISO 8601 string (from `alert_ingestion.startsAt`) or Unix timestamp
- `end`: defaults to `start + duration_minutes` when omitted
- Returns Prometheus `result` array as MCP content

### `requirements.txt`

```
mcp[cli]
httpx
```

### `Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
EXPOSE 5001
CMD ["python", "server.py"]
```

---

## Section 3 — Local Prometheus Stack (docker-compose)

### New services in `docker/docker-compose.yaml`

```yaml
  prometheus:
    image: prom/prometheus:v2.53.0
    container_name: conductor-prometheus
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    networks:
      - internal
    ports:
      - 9090:9090
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"

  node-exporter:
    image: prom/node-exporter:v1.8.1
    container_name: conductor-node-exporter
    networks:
      - internal
    pid: host
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - "--path.procfs=/host/proc"
      - "--path.sysfs=/host/sys"

  promql-mcp:
    build:
      context: ../z-plan/promql-mcp
    container_name: conductor-promql-mcp
    environment:
      - PROMETHEUS_URL=http://prometheus:9090
    networks:
      - internal
    ports:
      - 5001:5001
    depends_on:
      - prometheus
```

### New file: `docker/prometheus/prometheus.yml`

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: node
    static_configs:
      - targets: ["node-exporter:9100"]
```

---

## Validation Steps

1. `docker compose up -d` — all services start
2. Prometheus UI at `http://localhost:9090` — confirm `node_cpu_seconds_total` has data
3. Smoke-test MCP directly:
   ```bash
   curl -X POST http://localhost:5001/mcp \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"promql_query","arguments":{"expr":"up"}}}'
   ```
4. Register updated `auto_alert_recovery` workflow (v2)
5. Fire a `HighCPUUsage` test run with `prometheus_mcp_url: "http://localhost:5001/mcp"`
6. Confirm `query_prometheus_ref` status = `COMPLETED` and has metric output
7. Confirm `investigation_ref` prompt contains metric data

---

## What Does NOT Change

- `alert_action_executor` sub-workflow — untouched
- `human_review`, `ai_auto_execute`, `risk_assessment`, `verification` — untouched
- Vector DB / pgvector setup — untouched
- All existing workflow inputs remain valid; `prometheus_mcp_url` is additive

---

## Files Touched / Created

| File | Action |
|------|--------|
| `z-plan/auto_alert_recovery_workflow.json` | Update — add `query_prometheus`, `join_prometheus`, update `investigation` prompt, add `prometheus_mcp_url` input |
| `z-plan/auto_alert_recovery_plan.md` | Update — reflect new architecture |
| `z-plan/promql-mcp/server.py` | Create |
| `z-plan/promql-mcp/requirements.txt` | Create |
| `z-plan/promql-mcp/Dockerfile` | Create |
| `docker/docker-compose.yaml` | Update — add `prometheus`, `node-exporter`, `promql-mcp` services |
| `docker/prometheus/prometheus.yml` | Create |
