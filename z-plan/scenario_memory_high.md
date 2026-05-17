# POC Scenario: OOM / HighMemoryUsage → send alert report email

## Overview

| Field | Value |
|---|---|
| Alert | HighMemoryUsage — container `payment-api` at 92% memory (OOM imminent) |
| Alert source | AlertManager (`alert_payload.json`) |
| Risk level | HIGH → human review required |
| Action | `alert_action_executor` generates event report and sends email |
| Mail mock | HTTP POST to `https://httpbin.org/post` (no worker needed) |

---

## Step 0 — Setup (one-time)

### 0-1. Register task definitions

```bash
# No custom workers needed for this POC — send_alert_mail uses HTTP task
```

### 0-2. Seed the OOM runbook

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
      "runbook_text": "Runbook: HighMemoryUsage / OOM\nSymptom: Container memory usage above 90% for more than 10 minutes. OOM kill imminent.\nResolution:\n  1. Check current memory usage: docker stats <container> --no-stream\n  2. Inspect container logs for OOM indicators: docker logs --tail=100 <container>\n  3. If memory leak confirmed: restart the container to reclaim memory: docker restart <container>\n  4. Monitor memory after restart: docker stats <container> --no-stream\nRisk: HIGH - restarting a production container causes brief downtime."
    }
  }'
```

### 0-3. Register the workflows

```bash
# Register action sub-workflow first
curl -X POST http://localhost:8000/api/metadata/workflow \
  -H "Content-Type: application/json" \
  -d @z-plan/alert_action_executor_workflow.json

# Register main workflow
curl -X POST http://localhost:8000/api/metadata/workflow \
  -H "Content-Type: application/json" \
  -d @z-plan/auto_alert_recovery_workflow.json
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
    'vector_db_index': 'incidents',
    'recipient_email': 'kilicapeto@gmail.com'
  }
}))
")"
```

Save the returned `workflowId`:

```bash
WF_ID=<workflowId from response>
```

---

## Step 2 — Main workflow runs (automatic)

```
[COMPLETED] alert_ingestion_ref   alertname: HighMemoryUsage
                                  alert_severity: critical
                                  summary: "High memory usage on payment-api (92%)"

[COMPLETED] analyze_alert_ref     alert_type: HighMemoryUsage
                                  affected_service: payment-api
                                  potential_root_cause: Memory leak approaching OOM
                                  urgency: critical

[COMPLETED] doc_search_ref        Retrieved: Runbook HighMemoryUsage/OOM

[COMPLETED] investigation_ref     root_cause: Memory leak — container approaching OOM limit
                                  confidence_score: 0.87
                                  recommended_actions: ["docker restart payment-api"]
                                  affected_systems: ["payment-api"]

[COMPLETED] risk_assessment_ref   risk_level: HIGH
                                  risk_reason: Restarting production container causes brief downtime
                                  requires_human_approval: true

[COMPLETED] decision_router_ref   → HUMAN_REVIEW

[IN_PROGRESS] human_review_ref    ← workflow pauses here
```

---

## Step 3 — Complete the human review

```bash
TASK_ID=$(curl -s http://localhost:8000/api/workflow/$WF_ID | python3 -c "
import json, sys
w = json.load(sys.stdin)
for t in w['tasks']:
    if t['referenceTaskName'] == 'human_review_ref':
        print(t['taskId'])
")

curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d "{
    \"taskId\": \"$TASK_ID\",
    \"status\": \"COMPLETED\",
    \"outputData\": {
      \"approved\": true,
      \"note\": \"OOM risk confirmed — schedule restart during next maintenance window\",
      \"approved_by\": \"oncall@example.com\"
    }
  }"
```

---

## Step 4 — Action sub-workflow: generate report + mock mail

After human review completes:

```
[COMPLETED] join_review_ref
[COMPLETED] trigger_action_workflow_ref   workflowId: <action-wf-id>
[COMPLETED] verification_ref              status: TRIGGERED
```

Sub-workflow (`alert_action_executor`) runs:

```
[COMPLETED] generate_report_ref   (LLM_CHAT_COMPLETE)
              subject: "[CRITICAL] HighMemoryUsage — payment-api OOM risk on prod-cluster"
              body:
                Alert Summary
                =============
                Alert:     HighMemoryUsage
                Severity:  critical
                Container: payment-api (docker-host-01)
                Memory:    92% (3.68GB / 4GB) for >10 minutes
                Status:    firing since 2026-05-13T09:00:00Z

                Root Cause Analysis
                ===================
                Memory leak detected — container is approaching OOM limit.
                Confidence: 87%
                Affected systems: payment-api

                Risk Assessment
                ===============
                Risk Level: HIGH
                Reason: Restarting production container causes brief downtime.

                Recommended Actions
                ===================
                1. docker restart payment-api

                Review Outcome
                ==============
                Approved by: oncall@example.com
                Note: OOM risk confirmed — schedule restart during next maintenance window

[COMPLETED] send_alert_mail_ref   (HTTP → httpbin.org/post)
              response.statusCode: 200
              → mock confirms payload received
```

---

## Step 5 — Inspect the mock mail payload

```bash
ACTION_WF_ID=$(curl -s http://localhost:8000/api/workflow/$WF_ID | python3 -c "
import json, sys
w = json.load(sys.stdin)
for t in w['tasks']:
    if t['referenceTaskName'] == 'trigger_action_workflow_ref':
        print(t.get('outputData', {}).get('workflowId', ''))
")

curl -s http://localhost:8000/api/workflow/$ACTION_WF_ID | python3 -c "
import json, sys
w = json.load(sys.stdin)
print('sub-workflow status:', w['status'])
for t in w.get('tasks', []):
    if t['referenceTaskName'] == 'generate_report_ref':
        r = t.get('outputData', {}).get('result', {})
        print()
        print('=== EMAIL THAT WOULD BE SENT ===')
        print('To:     ', w['input']['recipient_email'])
        print('Subject:', r.get('subject'))
        print()
        print(r.get('body', ''))
"
```

---

## What to replace for production

| Component | POC | Production |
|---|---|---|
| `send_alert_mail` task type | `HTTP` → `httpbin.org/post` | `HTTP` → SendGrid / Mailgun / SES API |
| Authentication | none | `Authorization: Bearer <api-key>` header |
| No other changes needed | — | — |
