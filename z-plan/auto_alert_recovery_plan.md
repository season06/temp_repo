# auto_alert_recovery — Workflow Plan

## Architecture Overview

```
alert_ingestion (LLM_CHAT_COMPLETE)
        ↓
analyze_alert (LLM_CHAT_COMPLETE)
        ↓
doc_search (LLM_SEARCH_INDEX)          ← Vector DB runbook retrieval
        ↓
investigation (LLM_CHAT_COMPLETE)
        ↓
risk_assessment (LLM_CHAT_COMPLETE)    ← outputs: HIGH | MEDIUM | LOW
        ↓
decision_router (SWITCH, javascript)
   ├─ HIGH or MEDIUM → human_review (HUMAN task)
   └─ LOW (default) → ai_auto_execute (LLM_CHAT_COMPLETE)
        ↓
join_review (EXCLUSIVE_JOIN)           ← merges both review branches
        ↓
trigger_action_workflow (START_WORKFLOW)   ← always fires alert_action_executor
        ↓
verification (LLM_CHAT_COMPLETE)       ← confirms sub-workflow triggered
```

### `alert_action_executor` sub-workflow (scenario: send-mail)

```
generate_report (LLM_CHAT_COMPLETE)    ← builds email subject + body
        ↓
send_alert_mail (SIMPLE)               ← custom worker sends the email
```

---

## Task-by-Task Breakdown

### 1. `alert_ingestion` — `LLM_CHAT_COMPLETE`

- Normalize and enrich the raw AlertManager webhook payload into a structured format
- **Inputs:** `alert_source`, `alert_payload` (from `workflow.input`)
- **Outputs (in `result`):** `source`, `alertname`, `alert_severity`, `affected_instances`, `status`, `summary`, `description`, `startsAt`, `k8s_info`, `promql`
- `temperature: 0.1`, `maxTokens: 800`

### 2. `analyze_alert` — `LLM_CHAT_COMPLETE`

- AI extracts: `alert_type`, `affected_service`, `potential_root_cause`, `urgency`, `summary`
- Input: normalized payload from `alert_ingestion_ref.output.result`
- `temperature: 0.2`, `maxTokens: 1000`

### 3. `doc_search` — `LLM_SEARCH_INDEX`

- Queries the vector DB for relevant runbooks and past incident reports
- `query` = `analyze_alert_ref.output.result.summary`, `topK: 5`
- Config (`vectorDB`, `namespace`, `index`, `llmProvider`, `embedding_model`) passed as workflow inputs to stay provider-agnostic
- Marked `optional: true` — workflow continues if vector DB is unavailable

### 4. `investigation` — `LLM_CHAT_COMPLETE`

- Deep root-cause analysis combining alert analysis + retrieved docs
- Outputs: `root_cause`, `confidence_score`, `recommended_actions[]`, `estimated_impact`, `affected_systems[]`
- `temperature: 0.2`, `maxTokens: 2000`

### 5. `risk_assessment` — `LLM_CHAT_COMPLETE`

- Classifies remediation risk using defined criteria:
  - **HIGH** — data loss, production outage, or irreversible action
  - **MEDIUM** — service degradation, rollback complex
  - **LOW** — safe rollback, isolated, well-tested
- Outputs: `risk_level`, `risk_reason`, `auto_executable`, `requires_human_approval`
- `temperature: 0.1`, `maxTokens: 800`

### 6. `decision_router` — `SWITCH` (`evaluatorType: javascript`)

- Normalizes HIGH/MEDIUM → `"HUMAN_REVIEW"`, LOW → `"AUTO_EXECUTE"` via expression:
  ```javascript
  function evaluate() {
    var risk = $.risk_level;
    if (risk === 'HIGH' || risk === 'MEDIUM') { return 'HUMAN_REVIEW'; }
    return 'AUTO_EXECUTE';
  }
  evaluate();
  ```
- `decisionCases["HUMAN_REVIEW"]` → `human_review` task
- `defaultCase` → `ai_auto_execute` task

### 7a. `human_review` — `HUMAN`

- Workflow pauses; operator sees: `alertname`, `risk_level`, `risk_reason`, `root_cause`, `recommended_actions`, `affected_systems`, `estimated_impact`
- Operator approves or modifies the plan before proceeding

### 7b. `ai_auto_execute` — `LLM_CHAT_COMPLETE`

- AI selects safest action from `recommended_actions`
- Outputs: `selected_action`, `action_parameters`, `rollback_plan`, `approval_status: "AUTO_APPROVED"`
- `temperature: 0.1`, `maxTokens: 1000`

### `join_review` — `EXCLUSIVE_JOIN`

- `joinOn: ["human_review_ref", "ai_auto_execute_ref"]`
- `defaultExclusiveJoinTask: ["human_review_ref"]`
- Waits for whichever branch ran, then passes its output downstream

### 8. `trigger_action_workflow` — `START_WORKFLOW`

- **Always fires**, regardless of risk level or review outcome
- Starts `alert_action_executor` as an async sub-workflow
- Passes all triage context: `alertname`, `alert_data`, `analysis`, `investigation`, `risk_assessment`, `review_outcome`, `recipient_email`, `llm_provider`, `llm_model`
- Task completes immediately; sub-workflow runs independently
- Output: `workflowId` of the triggered sub-workflow

### 9. `verification` — `LLM_CHAT_COMPLETE`

- Confirms the sub-workflow was triggered and summarizes the triage outcome
- Outputs: `status` (always `TRIGGERED`), `confidence_score`, `summary`, `next_steps`
- `temperature: 0.1`, `maxTokens: 600`

---

## `alert_action_executor` Sub-Workflow (scenario: send-mail)

Defined in `alert_action_executor_workflow.json`. Can be swapped for different action scenarios without changing the main workflow.

### A. `generate_report` — `LLM_CHAT_COMPLETE`

- Builds a full alert analysis report formatted as an email
- Outputs (in `result`): `subject`, `body` (plain text with sections), `report_title`, `escalation_needed`
- `temperature: 0.2`, `maxTokens: 1500`

### B. `send_alert_mail` — `HTTP`

- No worker required — uses Conductor's built-in HTTP task
- **POC:** `POST https://httpbin.org/post` — echoes the payload, confirms the request was received
- **Production:** swap `uri` to your mail provider endpoint (SendGrid, Mailgun, SES, etc.) and add an `Authorization` header
- Inputs (as JSON body): `to`, `subject`, `body`, `escalation_needed`
- Output: `response.statusCode` (200 = success)

---

## Workflow-Level Config

| Field             | Value                    |
|-------------------|--------------------------|
| `name`            | `auto_alert_recovery`    |
| `version`         | `1`                      |
| `schemaVersion`   | `2`                      |
| `timeoutSeconds`  | `3600`                   |
| `timeoutPolicy`   | `TIME_OUT_WF`            |
| `ownerEmail`      | `kilicapeto@gmail.com`   |
| `restartable`     | `true`                   |

**Workflow inputs:**
`alertname`, `alert_source`, `alert_payload`, `alert_severity`, `alert_timestamp`,
`llm_provider`, `llm_model`, `embedding_model`,
`vector_db_provider`, `vector_db_namespace`, `vector_db_index`,
`recipient_email`

**Workflow outputs:**
`alertname`, `risk_level`, `action_workflow_id`, `verification_status`, `resolution_summary`

---

## Deliverables

| File | Description |
|------|-------------|
| `auto_alert_recovery_workflow.json` | Main workflow — POST to `/api/metadata/workflow` |
| `alert_action_executor_workflow.json` | Action sub-workflow (send-mail scenario) — POST to `/api/metadata/workflow` |

---

## Verification Steps

1. Register sub-workflow: `POST /api/metadata/workflow` with `alert_action_executor_workflow.json`
2. Register main workflow: `POST /api/metadata/workflow` with `auto_alert_recovery_workflow.json`
3. No workers needed — `send_alert_mail` is an HTTP task (POC uses `httpbin.org/post`)
4. **LOW risk test:** Start a run → confirm `ai_auto_execute` completes → `trigger_action_workflow` fires → sub-workflow generates report and POSTs to httpbin (status 200)
5. **HIGH risk test (OOM scenario):** Start a run with `alert_payload.json` → workflow pauses at `human_review` → complete the HUMAN task → confirm sub-workflow generates report and sends mock mail
6. Check sub-workflow status: `GET /api/workflow/<action_workflow_id>`
7. Inspect mock mail payload from `generate_report_ref` output in the sub-workflow
