# PromQL MCP Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a PromQL MCP server to the `auto_alert_recovery` workflow so live Prometheus metrics feed the investigation step, and provision a local Prometheus + node_exporter stack for end-to-end validation.

**Architecture:** A Python MCP server (`z-plan/promql-mcp/server.py`) exposes two tools — `promql_query` (instant) and `promql_query_range` (range) — that proxy to Prometheus's HTTP API. The workflow wraps the existing `doc_search` task and a new `query_prometheus` task in a `FORK_JOIN` so both run in parallel after `analyze_alert`; their results merge at a `JOIN` before `investigation`. Three Docker services (prometheus, node-exporter, promql-mcp) are added to `docker/docker-compose.yaml`.

**Tech Stack:** Python 3.12, `mcp[cli]` (FastMCP), `httpx`, pytest, pytest-asyncio, respx; Conductor `FORK_JOIN`/`JOIN`/`CALL_MCP_TOOL` system tasks; Docker Compose; prom/prometheus:v2.53.0; prom/node-exporter:v1.8.1

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `z-plan/promql-mcp/server.py` | Create | MCP server — two PromQL tools, httpx proxy to Prometheus |
| `z-plan/promql-mcp/requirements.txt` | Create | Runtime deps (mcp[cli], httpx) + test deps (pytest, pytest-asyncio, respx) |
| `z-plan/promql-mcp/Dockerfile` | Create | Container image for promql-mcp service |
| `z-plan/promql-mcp/tests/test_server.py` | Create | Unit tests for `_do_instant_query` and `_do_range_query` |
| `docker/docker-compose.yaml` | Modify | Add prometheus, node-exporter, promql-mcp services |
| `docker/prometheus/prometheus.yml` | Create | Scrape config targeting node-exporter |
| `z-plan/auto_alert_recovery_workflow.json` | Modify | Add FORK_JOIN, JOIN, query_prometheus task; update investigation prompt; add prometheus_mcp_url input |
| `z-plan/auto_alert_recovery_plan.md` | Modify | Update architecture diagram to reflect new tasks |

---

## Task 1: PromQL MCP server — internal query functions

These are the testable core functions. The `@mcp.tool()` wrappers in Task 2 call them.

**Files:**
- Create: `z-plan/promql-mcp/server.py`
- Create: `z-plan/promql-mcp/tests/__init__.py`
- Create: `z-plan/promql-mcp/tests/test_server.py`
- Create: `z-plan/promql-mcp/requirements.txt`

- [ ] **Step 1.1: Create `requirements.txt`**

```
mcp[cli]
httpx
pytest
pytest-asyncio
respx
```

- [ ] **Step 1.2: Create `z-plan/promql-mcp/tests/__init__.py`** (empty file)

- [ ] **Step 1.3: Write failing tests**

Create `z-plan/promql-mcp/tests/test_server.py`:

```python
import pytest
import respx
import httpx
from urllib.parse import parse_qs, urlparse
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from server import _do_instant_query, _do_range_query

FAKE = "http://fake-prometheus:9090"

INSTANT_RESPONSE = {
    "status": "success",
    "data": {
        "resultType": "vector",
        "result": [{"metric": {"instance": "host1"}, "value": [1234567890, "95.5"]}],
    },
}

RANGE_RESPONSE = {
    "status": "success",
    "data": {
        "resultType": "matrix",
        "result": [{"metric": {}, "values": [[1234567890, "90"], [1234567950, "92"]]}],
    },
}


@pytest.mark.asyncio
@respx.mock
async def test_instant_query_calls_query_endpoint():
    route = respx.get(f"{FAKE}/api/v1/query").mock(
        return_value=httpx.Response(200, json=INSTANT_RESPONSE)
    )
    result = await _do_instant_query(
        expr="100*(1-avg by(instance)(irate(node_cpu_seconds_total{mode='idle'}[5m])))",
        prometheus_url=FAKE,
    )
    assert route.called
    assert result["status"] == "success"
    assert result["result"][0]["value"][1] == "95.5"


@pytest.mark.asyncio
@respx.mock
async def test_instant_query_passes_time_param():
    route = respx.get(f"{FAKE}/api/v1/query").mock(
        return_value=httpx.Response(200, json=INSTANT_RESPONSE)
    )
    await _do_instant_query(expr="up", time="1698400000", prometheus_url=FAKE)
    params = parse_qs(urlparse(str(route.calls[0].request.url)).query)
    assert params["time"][0] == "1698400000"


@pytest.mark.asyncio
@respx.mock
async def test_range_query_converts_iso_timestamp():
    route = respx.get(f"{FAKE}/api/v1/query_range").mock(
        return_value=httpx.Response(200, json=RANGE_RESPONSE)
    )
    result = await _do_range_query(
        expr="up",
        start="2023-10-27T10:00:00Z",
        duration_minutes=30,
        prometheus_url=FAKE,
    )
    assert route.called
    assert result["status"] == "success"
    params = parse_qs(urlparse(str(route.calls[0].request.url)).query)
    assert "start" in params
    assert "end" in params
    assert float(params["end"][0]) > float(params["start"][0])


@pytest.mark.asyncio
@respx.mock
async def test_range_query_end_is_start_plus_duration():
    route = respx.get(f"{FAKE}/api/v1/query_range").mock(
        return_value=httpx.Response(200, json=RANGE_RESPONSE)
    )
    await _do_range_query(
        expr="up",
        start="2023-10-27T10:00:00Z",
        duration_minutes=15,
        prometheus_url=FAKE,
    )
    params = parse_qs(urlparse(str(route.calls[0].request.url)).query)
    start_ts = float(params["start"][0])
    end_ts = float(params["end"][0])
    assert abs((end_ts - start_ts) - 15 * 60) < 1


@pytest.mark.asyncio
@respx.mock
async def test_range_query_explicit_end_overrides_duration():
    route = respx.get(f"{FAKE}/api/v1/query_range").mock(
        return_value=httpx.Response(200, json=RANGE_RESPONSE)
    )
    await _do_range_query(
        expr="up",
        start="2023-10-27T10:00:00Z",
        end="2023-10-27T10:05:00Z",
        duration_minutes=30,
        prometheus_url=FAKE,
    )
    params = parse_qs(urlparse(str(route.calls[0].request.url)).query)
    start_ts = float(params["start"][0])
    end_ts = float(params["end"][0])
    assert abs((end_ts - start_ts) - 5 * 60) < 1
```

- [ ] **Step 1.4: Run tests — expect ImportError (server.py not yet created)**

```bash
cd /home/xizhen/conductor/z-plan/promql-mcp
pip install -r requirements.txt -q
pytest tests/ -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'server'`

- [ ] **Step 1.5: Create `z-plan/promql-mcp/server.py` with internal functions**

```python
from mcp.server.fastmcp import FastMCP
import httpx
import os
from datetime import datetime, timedelta, timezone

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
mcp = FastMCP("promql")


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
    mcp.run(transport="streamable-http", host="0.0.0.0", port=5001)
```

- [ ] **Step 1.6: Run tests — expect all pass**

```bash
cd /home/xizhen/conductor/z-plan/promql-mcp
pytest tests/ -v
```

Expected output:
```
tests/test_server.py::test_instant_query_calls_query_endpoint PASSED
tests/test_server.py::test_instant_query_passes_time_param PASSED
tests/test_server.py::test_range_query_converts_iso_timestamp PASSED
tests/test_server.py::test_range_query_end_is_start_plus_duration PASSED
tests/test_server.py::test_range_query_explicit_end_overrides_duration PASSED
5 passed
```

- [ ] **Step 1.7: Commit**

```bash
cd /home/xizhen/conductor
git add z-plan/promql-mcp/server.py z-plan/promql-mcp/requirements.txt z-plan/promql-mcp/tests/
git commit -m "feat: add PromQL MCP server with instant and range query tools"
```

---

## Task 2: Dockerfile for promql-mcp

**Files:**
- Create: `z-plan/promql-mcp/Dockerfile`

- [ ] **Step 2.1: Create `z-plan/promql-mcp/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir mcp[cli] httpx
COPY server.py .
EXPOSE 5001
CMD ["python", "server.py"]
```

Note: the Dockerfile installs only runtime deps (not pytest/respx).

- [ ] **Step 2.2: Build the image to verify it compiles**

```bash
cd /home/xizhen/conductor/z-plan/promql-mcp
docker build -t conductor-promql-mcp:local .
```

Expected: `Successfully built <id>` with no errors.

- [ ] **Step 2.3: Commit**

```bash
cd /home/xizhen/conductor
git add z-plan/promql-mcp/Dockerfile
git commit -m "feat: add Dockerfile for promql-mcp service"
```

---

## Task 3: Add Prometheus stack to docker-compose

**Files:**
- Modify: `docker/docker-compose.yaml`
- Create: `docker/prometheus/prometheus.yml`

- [ ] **Step 3.1: Create `docker/prometheus/prometheus.yml`**

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: node
    static_configs:
      - targets: ["node-exporter:9100"]
```

- [ ] **Step 3.2: Add three services to `docker/docker-compose.yaml`**

Open `docker/docker-compose.yaml`. Add the following three service blocks inside the `services:` section, before the `volumes:` key:

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

- [ ] **Step 3.3: Start the new services**

```bash
cd /home/xizhen/conductor/docker
docker compose up -d prometheus node-exporter promql-mcp
```

Expected: all three containers reach `Started` state.

- [ ] **Step 3.4: Verify Prometheus has node metrics**

```bash
sleep 20  # wait for first scrape
curl -s "http://localhost:9090/api/v1/query?query=up" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('status:', d['status'])
for r in d['data']['result']:
    print(' ', r['metric'].get('job','?'), r['value'][1])
"
```

Expected:
```
status: success
  node 1
```

- [ ] **Step 3.5: Verify MCP server responds**

```bash
curl -s -X POST http://localhost:5001/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | python3 -m json.tool
```

Expected: response contains `"name": "promql_query"` and `"name": "promql_query_range"` in the tools list.

- [ ] **Step 3.6: Smoke-test a live PromQL call through MCP**

```bash
curl -s -X POST http://localhost:5001/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"promql_query","arguments":{"expr":"up"}}}' \
  | python3 -m json.tool
```

Expected: response has `"content"` with metric data and no `"error"` field.

- [ ] **Step 3.7: Commit**

```bash
cd /home/xizhen/conductor
git add docker/docker-compose.yaml docker/prometheus/prometheus.yml
git commit -m "feat: add prometheus, node-exporter, and promql-mcp to docker-compose"
```

---

## Task 4: Update `auto_alert_recovery` workflow

**Files:**
- Modify: `z-plan/auto_alert_recovery_workflow.json`
- Modify: `z-plan/auto_alert_recovery_plan.md`

### What changes

1. Add `"prometheus_mcp_url"` to `inputParameters` array (top-level)
2. Replace the standalone `doc_search` task with a `FORK_JOIN` that runs `doc_search` and `query_prometheus` in parallel
3. Add a `JOIN` task after the fork
4. Update `investigation`'s user message to include metric data

- [ ] **Step 4.1: Add `prometheus_mcp_url` to workflow `inputParameters`**

In `z-plan/auto_alert_recovery_workflow.json`, find the `inputParameters` array (lines 10-23). Add `"prometheus_mcp_url"` as the last element:

```json
  "inputParameters": [
    "alertname",
    "alert_source",
    "alert_payload",
    "alert_severity",
    "alert_timestamp",
    "llm_provider",
    "llm_model",
    "embedding_model",
    "vector_db_provider",
    "vector_db_namespace",
    "vector_db_index",
    "recipient_email",
    "prometheus_mcp_url"
  ],
```

- [ ] **Step 4.2: Replace `doc_search` task with FORK_JOIN**

Find the `doc_search` task object (from `"name": "doc_search"` to its closing `}`). Replace it with the following three tasks (FORK_JOIN, the two forked tasks inside it, plus the JOIN):

```json
    {
      "name": "fork_data_gathering",
      "taskReferenceName": "fork_data_gathering_ref",
      "type": "FORK_JOIN",
      "description": "Run runbook search and Prometheus metric query in parallel",
      "forkTasks": [
        [
          {
            "name": "doc_search",
            "taskReferenceName": "doc_search_ref",
            "type": "LLM_SEARCH_INDEX",
            "description": "Search vector DB for relevant runbooks and past incident reports",
            "optional": true,
            "inputParameters": {
              "vectorDB": "${workflow.input.vector_db_provider}",
              "namespace": "${workflow.input.vector_db_namespace}",
              "index": "${workflow.input.vector_db_index}",
              "query": "${analyze_alert_ref.output.result.summary}",
              "llmMaxResults": 5,
              "embeddingModelProvider": "${workflow.input.llm_provider}",
              "embeddingModel": "${workflow.input.embedding_model}"
            }
          }
        ],
        [
          {
            "name": "query_prometheus",
            "taskReferenceName": "query_prometheus_ref",
            "type": "CALL_MCP_TOOL",
            "description": "Query Prometheus for live metric data using the extracted PromQL expression",
            "optional": true,
            "inputParameters": {
              "mcpServer": "${workflow.input.prometheus_mcp_url}",
              "method": "promql_query_range",
              "expr": "${alert_ingestion_ref.output.result.promql}",
              "start": "${alert_ingestion_ref.output.result.startsAt}",
              "duration_minutes": 30
            }
          }
        ]
      ]
    },
    {
      "name": "join_data_gathering",
      "taskReferenceName": "join_prometheus_ref",
      "type": "JOIN",
      "description": "Wait for both doc_search and query_prometheus to complete",
      "joinOn": ["doc_search_ref", "query_prometheus_ref"]
    },
```

- [ ] **Step 4.3: Update `investigation` user message**

Find the `investigation` task's user message (currently ends with `...${doc_search_ref.output.result}"`). Replace just the `"message"` value in the `user` role object:

```json
          {
            "role": "user",
            "message": "Alert Analysis: ${analyze_alert_ref.output.result}\nRelevant Runbooks: ${doc_search_ref.output.result}\nPrometheus Metric Data: ${query_prometheus_ref.output.content}"
          }
```

- [ ] **Step 4.4: Register the updated workflow on the local Conductor server**

```bash
curl -s -X POST http://localhost:8000/api/metadata/workflow \
  -H "Content-Type: application/json" \
  -d @/home/xizhen/conductor/z-plan/auto_alert_recovery_workflow.json \
  | python3 -m json.tool
```

Expected: HTTP 200 with no error body, or a message confirming workflow registered.

If you get a 409 (already exists at version 1), bump `"version"` to `2` in the JSON and retry. Also update the curl invocation in `run_auto_alert_recovery.md` to use version 2.

- [ ] **Step 4.5: Update `z-plan/auto_alert_recovery_plan.md` architecture section**

Find the architecture diagram block (lines 5-25). Replace it with:

```
alert_ingestion (LLM_CHAT_COMPLETE)
        ↓
analyze_alert (LLM_CHAT_COMPLETE)
        ↓
fork_data_gathering (FORK_JOIN)
   ├─ doc_search (LLM_SEARCH_INDEX, optional)    ← Vector DB runbook retrieval
   └─ query_prometheus (CALL_MCP_TOOL, optional) ← Live metric data from Prometheus MCP
        ↓
join_data_gathering (JOIN)
        ↓
investigation (LLM_CHAT_COMPLETE)              ← now includes Prometheus metric data
        ↓
risk_assessment (LLM_CHAT_COMPLETE)            ← outputs: HIGH | MEDIUM | LOW
        ↓
decision_router (SWITCH, javascript)
   ├─ HIGH or MEDIUM → human_review (HUMAN task)
   └─ LOW (default) → ai_auto_execute (LLM_CHAT_COMPLETE)
        ↓
join_review (EXCLUSIVE_JOIN)
        ↓
trigger_action_workflow (START_WORKFLOW)   ← always fires alert_action_executor
        ↓
verification (LLM_CHAT_COMPLETE)           ← confirms sub-workflow triggered
```

- [ ] **Step 4.6: Commit**

```bash
cd /home/xizhen/conductor
git add z-plan/auto_alert_recovery_workflow.json z-plan/auto_alert_recovery_plan.md
git commit -m "feat: add PromQL MCP query step to auto_alert_recovery workflow"
```

---

## Task 5: End-to-end validation

No code changes — this task validates the entire integration works.

- [ ] **Step 5.1: Confirm all services are running**

```bash
docker ps --format "table {{.Names}}\t{{.Status}}" | grep conductor
```

Expected: `conductor-server`, `conductor-promql-mcp`, `conductor-prometheus`, `conductor-node-exporter` all `Up`.

- [ ] **Step 5.2: Fire a test workflow run with `prometheus_mcp_url`**

```bash
WORKFLOW_ID=$(curl -s -X POST http://localhost:8000/api/workflow/execute/auto_alert_recovery/1 \
  -H "Content-Type: application/json" \
  -d '{
    "name": "auto_alert_recovery",
    "version": 1,
    "input": {
      "alert_source": "alertmanager",
      "alert_payload": "{\"version\":\"4\",\"status\":\"firing\",\"groupLabels\":{\"alertname\":\"HighCPUUsage\"},\"commonLabels\":{\"alertname\":\"HighCPUUsage\",\"severity\":\"critical\",\"cluster\":\"prod-cluster\"},\"commonAnnotations\":{\"summary\":\"High CPU usage detected across multiple instances\"},\"externalURL\":\"http://alertmanager.example.com\",\"alerts\":[{\"status\":\"firing\",\"labels\":{\"alertname\":\"HighCPUUsage\",\"severity\":\"critical\",\"cluster\":\"prod-cluster\",\"instance\":\"web-server-01\"},\"annotations\":{\"description\":\"CPU usage on web-server-01 is at 95% for more than 5 minutes.\"},\"startsAt\":\"2023-10-27T10:00:00.000Z\",\"generatorURL\":\"http://prometheus.example.com/graph?g0.expr=100+%2A+%281+-+avg+by%28instance%29+%28irate%28node_cpu_seconds_total%7Bmode%3D%22idle%22%7D%5B5m%5D%29%29+%3E+90\",\"fingerprint\":\"a1b2c3d4e5f6g7h8\"}]}",
      "llm_provider": "openai",
      "llm_model": "gpt-4o-mini",
      "embedding_model": "text-embedding-3-small",
      "vector_db_provider": "pgvector-local",
      "vector_db_namespace": "runbooks",
      "vector_db_index": "incidents",
      "recipient_email": "oncall@example.com",
      "prometheus_mcp_url": "http://conductor-promql-mcp:5001/mcp"
    }
  }' | python3 -c "import json,sys; print(json.load(sys.stdin).get('workflowId','ERROR'))")
echo "Workflow ID: $WORKFLOW_ID"
```

Note: use `conductor-promql-mcp:5001` (Docker internal hostname) because conductor-server is inside the `internal` network.

- [ ] **Step 5.3: Poll until past the fork/join (allow 2 minutes for LLM tasks)**

```bash
sleep 30
curl -s http://localhost:8000/api/workflow/$WORKFLOW_ID | python3 -c "
import json, sys
w = json.load(sys.stdin)
print('status:', w['status'])
for t in w.get('tasks', []):
    print(f'  [{t[\"status\"]:14}] {t[\"referenceTaskName\"]} ({t[\"taskType\"]})')
"
```

Expected task sequence up to investigation:
```
  [COMPLETED    ] alert_ingestion_ref        (LLM_CHAT_COMPLETE)
  [COMPLETED    ] analyze_alert_ref          (LLM_CHAT_COMPLETE)
  [COMPLETED    ] fork_data_gathering_ref    (FORK_JOIN)
  [COMPLETED    ] doc_search_ref             (LLM_SEARCH_INDEX)
  [COMPLETED    ] query_prometheus_ref       (CALL_MCP_TOOL)
  [COMPLETED    ] join_prometheus_ref        (JOIN)
  [COMPLETED    ] investigation_ref          (LLM_CHAT_COMPLETE)
```

- [ ] **Step 5.4: Confirm `query_prometheus_ref` output contains metric data**

```bash
curl -s http://localhost:8000/api/workflow/$WORKFLOW_ID | python3 -c "
import json, sys
w = json.load(sys.stdin)
for t in w['tasks']:
    if t['referenceTaskName'] == 'query_prometheus_ref':
        print('status:', t['status'])
        print('output:', json.dumps(t.get('outputData', {}), indent=2)[:500])
"
```

Expected: `status: COMPLETED` and `outputData.content` contains a non-empty result array.

- [ ] **Step 5.5: Confirm `investigation_ref` prompt included metric data**

```bash
curl -s http://localhost:8000/api/workflow/$WORKFLOW_ID | python3 -c "
import json, sys
w = json.load(sys.stdin)
for t in w['tasks']:
    if t['referenceTaskName'] == 'investigation_ref':
        inp = t.get('inputData', {})
        msgs = inp.get('messages', [])
        for m in msgs:
            if m.get('role') == 'user':
                body = m.get('message', '')
                print('has Prometheus data:', 'Prometheus Metric Data' in body)
                print('metric snippet:', body[body.find('Prometheus'):body.find('Prometheus')+80])
"
```

Expected: `has Prometheus data: True`
