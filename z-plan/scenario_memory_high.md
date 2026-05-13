# Scenario: HighMemoryUsage → docker restart

## Overview

| Field | Value |
|---|---|
| Alert | HighMemoryUsage — container `payment-api` at 92% memory for 10 min |
| Alert source | AlertManager (`alert_payload.json`) |
| Runbook action | `docker restart payment-api` |
| Risk level | HIGH → human review required |
| Execution | `execute_action_worker.py` runs the approved docker command |

---

## Step 0 — Setup

### 0-1. Start a test container (safe to restart)

```bash
docker run -d --name payment-api alpine sleep infinity
```

### 0-2. Seed the memory high runbook

```bash
curl -X POST http://localhost:8000/api/workflow/execute/seed_runbooks/1 \
  -H "Content-Type: application/json" \
  -d '{
    "name": "seed_runbooks",
    "version": 1,
    "input": {
      "llm_provider": "openai",
      "embedding_model": "text-embedding-3-small",
      "vector_db_provider": "pgvector-local",
      "vector_db_namespace": "runbooks",
      "vector_db_index": "incidents",
      "runbook_id": "runbook_high_memory_usage",
      "runbook_text": "Runbook: HighMemoryUsage\nSymptom: Container memory usage above 90% for more than 10 minutes. Possible memory leak.\nResolution:\n  1. Check current memory usage: docker stats <container> --no-stream\n  2. Inspect container logs for OOM indicators: docker logs --tail=100 <container>\n  3. If memory leak confirmed: restart the container to reclaim memory: docker restart <container>\n  4. Monitor memory after restart: docker stats <container> --no-stream\nRisk: HIGH - restarting a production container causes brief downtime."
    }
  }'
```

### 0-3. Start the execute_action worker

```bash
cd z-plan
pip install requests   # one-time
python3 execute_action_worker.py
```

Worker output on start:
```
execute_action worker ready
  Conductor : http://localhost:8000
  Task type : execute_action
  Worker ID : execute-action-worker-01
  Allowed   : docker restart <container>
```

---

## Step 1 — Start the workflow

```bash
curl -X POST http://localhost:8000/api/workflow/execute/auto_alert_recovery/1 \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "
import json
payload = open('z-plan/alert_payload.json').read()
print(json.dumps({
  'name': 'auto_alert_recovery',
  'version': 1,
  'input': {
    'alert_source': 'alertmanager',
    'alert_payload': payload,
    'llm_provider': 'openai',
    'llm_model': 'gpt-4o-mini',
    'embedding_model': 'text-embedding-3-small',
    'vector_db_provider': 'pgvector-local',
    'vector_db_namespace': 'runbooks',
    'vector_db_index': 'incidents'
  }
}))
")"
```

---

## Expected Task Flow

```
[COMPLETED] alert_ingestion_ref  (LLM_CHAT_COMPLETE)
              alertname: HighMemoryUsage
              alert_severity: critical
              affected_instances: ["docker-host-01"]
              promql: container_memory_usage_bytes{container="payment-api"} / ... > 0.9

[COMPLETED] analyze_alert_ref    (LLM_CHAT_COMPLETE)
              alert_type: HighMemoryUsage
              affected_service: payment-api
              potential_root_cause: Memory leak in payment-api container
              urgency: critical

[COMPLETED] doc_search_ref       (LLM_SEARCH_INDEX)
              result: [Runbook: HighMemoryUsage → docker restart <container>]

[COMPLETED] investigation_ref    (LLM_CHAT_COMPLETE)
              root_cause: Memory leak causing container to approach OOM limit
              recommended_actions: ["docker restart payment-api"]
              confidence_score: 0.85

[COMPLETED] risk_assessment_ref  (LLM_CHAT_COMPLETE)
              risk_level: HIGH
              risk_reason: Restarting production container causes brief downtime
              requires_human_approval: true

[COMPLETED] decision_router_ref  (SWITCH)
              → HUMAN_REVIEW

[IN_PROGRESS] human_review_ref   (HUMAN)   ← workflow pauses here
```

---

## Step 2 — Complete the human review

### 2-1. Get the human_review task ID

```bash
WF_ID=<your-workflow-id>

TASK_ID=$(curl -s http://localhost:8000/api/workflow/$WF_ID | python3 -c "
import json, sys
w = json.load(sys.stdin)
for t in w['tasks']:
    if t['referenceTaskName'] == 'human_review_ref':
        print(t['taskId'])
")
echo "task ID: $TASK_ID"
```

### 2-2. Approve the restart action

```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d "{
    \"taskId\": \"$TASK_ID\",
    \"status\": \"COMPLETED\",
    \"outputData\": {
      \"approved\": true,
      \"selected_action\": \"docker restart payment-api\",
      \"approved_by\": \"oncall-engineer@company.com\",
      \"approval_note\": \"Memory leak confirmed in logs, safe to restart during low-traffic window\"
    }
  }"
```

---

## Step 3 — Worker executes the action

The `execute_action_worker.py` picks up the `execute_action` task, validates the command, and runs:

```bash
docker restart payment-api
```

Then checks container status:
```bash
docker inspect --format {{.State.Status}} payment-api
# → running
```

Worker logs:
```
[<task-id>] received task
[<task-id>] action_plan: {"approved": true, "selected_action": "docker restart payment-api", ...}
[<task-id>] executing: docker restart payment-api
[<task-id>] done — status=COMPLETED, container=running
```

Task output written back to Conductor:
```json
{
  "action_taken": "docker restart payment-api",
  "execution_result": "payment-api",
  "exit_code": 0,
  "container_name": "payment-api",
  "container_status_after": "running",
  "success": true
}
```

---

## Step 4 — Verification

```
[COMPLETED] verification_ref     (LLM_CHAT_COMPLETE)
              status: RESOLVED
              confidence_score: 0.95
              summary: Container payment-api restarted successfully and is running.
                       Memory usage reset. No further action required.
              next_steps: []
```

---

## Worker Safety Rules

The worker only accepts commands matching exactly:

```
docker restart <container-name>
```

Any other command (e.g. `docker rm`, `kubectl delete`, shell injection) is rejected with `FAILED` status before execution.

---

## Files

| File | Description |
|---|---|
| `alert_payload.json` | AlertManager webhook payload — HighMemoryUsage, container payment-api |
| `auto_alert_recovery_workflow.json` | Workflow definition |
| `execute_action_worker.py` | Worker that polls and runs docker restart |
| `seed_runbooks_workflow.json` | Workflow to index runbooks into pgvector |
| `seed_runbooks_docs.md` | Runbook seeding reference with examples |
| `run_auto_alert_recovery.md` | How to start the workflow with curl |
