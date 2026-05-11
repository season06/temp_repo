# How to Start `auto_alert_recovery` with curl

## Endpoint

```
POST http://localhost:8000/api/workflow/execute/auto_alert_recovery/1
Content-Type: application/json
```

Body must be a `StartWorkflowRequest` — alert payload and config go inside `"input": {}`.

---

## Full Example — AlertManager Webhook Payload

```bash
curl -X POST http://localhost:8000/api/workflow/execute/auto_alert_recovery/1 \
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
      "vector_db_index": "incidents"
    }
  }'
```

## From a File (recommended)

If your alert payload is a JSON file (e.g. `alert_payload.json`), use Python to embed it cleanly:

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

## Input Parameters

| Parameter              | Required | Description |
|------------------------|----------|-------------|
| `alert_source`         | yes      | Origin of the alert (e.g. `alertmanager`) |
| `alert_payload`        | yes      | Raw AlertManager webhook JSON, as a string |
| `llm_provider`         | yes      | LLM provider name (e.g. `openai`) |
| `llm_model`            | yes      | Chat model (e.g. `gpt-4o-mini`) |
| `embedding_model`      | yes      | Embedding model for vector search (e.g. `text-embedding-3-small`) |
| `vector_db_provider`   | yes      | Registered vector DB name (e.g. `pgvector-local`) |
| `vector_db_namespace`  | yes      | Namespace in the vector DB (e.g. `runbooks`) |
| `vector_db_index`      | yes      | Index/table name (e.g. `incidents`) |

---

## Response

```json
{
  "workflowId": "bce3c5e0-cdde-460e-a784-e5d3a89c9c42",
  "targetWorkflowStatus": "RUNNING",
  ...
}
```

---

## Check Workflow Status

```bash
curl http://localhost:8000/api/workflow/<workflowId>
```

### Pretty-print task states

```bash
curl -s http://localhost:8000/api/workflow/<workflowId> | python3 -c "
import json, sys
w = json.load(sys.stdin)
print('status:', w['status'])
for t in w.get('tasks', []):
    print(f'  [{t[\"status\"]:14}] {t[\"referenceTaskName\"]} ({t[\"taskType\"]})')
"
```

---

## Expected Task Flow

```
[COMPLETED    ] alert_normalizer_ref  (LLM_CHAT_COMPLETE)   ← normalize AlertManager payload
[COMPLETED    ] analyze_alert_ref     (LLM_CHAT_COMPLETE)   ← extract type, service, root cause
[COMPLETED    ] doc_search_ref        (LLM_SEARCH_INDEX)    ← retrieve matching runbooks
[COMPLETED    ] investigation_ref     (LLM_CHAT_COMPLETE)   ← root cause + recommended actions
[COMPLETED    ] risk_assessment_ref   (LLM_CHAT_COMPLETE)   ← HIGH | MEDIUM | LOW
[COMPLETED    ] decision_router_ref   (SWITCH)
    ├─ HIGH/MEDIUM → [IN_PROGRESS ] human_review_ref  (HUMAN)          ← workflow pauses
    └─ LOW         → [COMPLETED   ] ai_auto_execute_ref (LLM_CHAT_COMPLETE)
[COMPLETED    ] join_review_ref       (EXCLUSIVE_JOIN)
[SCHEDULED    ] execute_action_ref    (SIMPLE)               ← needs kubectl worker
[COMPLETED    ] verification_ref      (LLM_CHAT_COMPLETE)
```

---

## Complete the HUMAN Review Task (HIGH/MEDIUM risk)

When the workflow pauses at `human_review_ref`, complete it via:

```bash
# 1. Get the task ID
TASK_ID=$(curl -s http://localhost:8000/api/workflow/<workflowId> | \
  python3 -c "
import json, sys
w = json.load(sys.stdin)
for t in w['tasks']:
    if t['referenceTaskName'] == 'human_review_ref':
        print(t['taskId'])
")

# 2. Approve with selected action
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d "{
    \"taskId\": \"$TASK_ID\",
    \"status\": \"COMPLETED\",
    \"outputData\": {
      \"approved\": true,
      \"selected_action\": \"kubectl scale deployment/web-server --replicas=6 -n production\",
      \"approved_by\": \"oncall-engineer@company.com\",
      \"approval_note\": \"Scaling out to handle traffic spike\"
    }
  }"
```

---

## Prerequisites

Before running, ensure runbooks are seeded:

```bash
# See z-plan/seed_runbooks_docs.md for full examples
curl -X POST http://localhost:8000/api/workflow/execute/seed_runbooks/1 \
  -H "Content-Type: application/json" \
  -d '{ "name": "seed_runbooks", "version": 1, "input": { ... } }'
```
