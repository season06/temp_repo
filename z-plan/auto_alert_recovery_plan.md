# auto_alert_recovery — Workflow Plan

## Architecture Overview

```
alert_ingestion (SIMPLE)
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
join_review (EXCLUSIVE_JOIN)           ← merges both branches
        ↓
execute_action (SIMPLE)
        ↓
verification (LLM_CHAT_COMPLETE)
```

---

## Task-by-Task Breakdown

### 1. `alert_ingestion` — `SIMPLE`

- Normalize and deduplicate the raw alert payload
- **Inputs:** `alert_id`, `alert_source`, `alert_payload`, `alert_severity`, `alert_timestamp` (all from `workflow.input`)
- **Outputs:** `alert_id`, `source`, `normalized_payload`, `alert_severity`
- Requires a custom worker polling the `alert_ingestion` task queue

### 2. `analyze_alert` — `LLM_CHAT_COMPLETE`

- AI extracts: `alert_type`, `affected_service`, `potential_root_cause`, `urgency`, `summary`
- Input: normalized payload from `alert_ingestion_ref.output`
- `temperature: 0.2`, `maxTokens: 1000`

### 3. `doc_search` — `LLM_SEARCH_INDEX`

- Queries the vector DB for relevant runbooks and past incident reports
- `query` = `analyze_alert_ref.output.result.summary`, `topK: 5`
- Config (`vectorDB`, `namespace`, `index`, `llmProvider`, `embedding_model`) passed as workflow inputs to stay provider-agnostic

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
    var risk = $.risk_assessment_ref['output']['result']['risk_level'];
    if (risk === 'HIGH' || risk === 'MEDIUM') { return 'HUMAN_REVIEW'; }
    return 'AUTO_EXECUTE';
  }
  evaluate();
  ```
- `decisionCases["HUMAN_REVIEW"]` → `human_review` task
- `defaultCase` → `ai_auto_execute` task

### 7a. `human_review` — `HUMAN`

- Workflow pauses; operator sees: `alert_id`, `risk_level`, `risk_reason`, `root_cause`, `recommended_actions`, `affected_systems`
- Operator approves or modifies the execution plan before proceeding

### 7b. `ai_auto_execute` — `LLM_CHAT_COMPLETE`

- AI selects safest action from `recommended_actions`
- Outputs: `selected_action`, `action_parameters`, `rollback_plan`, `approval_status: "AUTO_APPROVED"`
- `temperature: 0.1`, `maxTokens: 1000`

### `join_review` — `EXCLUSIVE_JOIN`

- `joinOn: ["human_review_ref", "ai_auto_execute_ref"]`
- `defaultExclusiveJoinTask: ["human_review_ref"]`
- Waits for whichever branch ran, then passes its output downstream

### 8. `execute_action` — `SIMPLE`

- Executes the approved remediation against the target system
- Inputs: `alert_id`, `action_plan` (from `join_review_ref.output`), `affected_systems`
- Outputs: `action_taken`, `execution_result`, `execution_timestamp`
- Requires a custom worker polling the `execute_action` task queue

### 9. `verification` — `LLM_CHAT_COMPLETE`

- Determines if remediation resolved the alert
- Outputs: `status (RESOLVED|PARTIAL|FAILED)`, `confidence_score`, `summary`, `next_steps`
- `temperature: 0.1`, `maxTokens: 800`

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
`alert_id`, `alert_source`, `alert_payload`, `alert_severity`, `alert_timestamp`,
`llm_provider`, `llm_model`, `embedding_model`,
`vector_db_provider`, `vector_db_namespace`, `vector_db_index`

**Workflow outputs:**
`alert_id`, `risk_level`, `action_taken`, `verification_status`, `resolution_summary`

---

## Task Definitions Required (SIMPLE workers)

Two `TaskDef` objects must be registered before the workflow can run:

### `alert_ingestion`
```json
{
  "name": "alert_ingestion",
  "retryCount": 3,
  "retryLogic": "EXPONENTIAL_BACKOFF",
  "timeoutSeconds": 60,
  "responseTimeoutSeconds": 30,
  "ownerEmail": "kilicapeto@gmail.com",
  "inputKeys": ["alert_id", "alert_source", "alert_payload", "alert_severity", "alert_timestamp"],
  "outputKeys": ["alert_id", "source", "normalized_payload", "alert_severity"]
}
```

### `execute_action`
```json
{
  "name": "execute_action",
  "retryCount": 1,
  "retryLogic": "FIXED",
  "timeoutSeconds": 300,
  "responseTimeoutSeconds": 240,
  "ownerEmail": "kilicapeto@gmail.com",
  "inputKeys": ["alert_id", "action_plan", "affected_systems"],
  "outputKeys": ["action_taken", "execution_result", "execution_timestamp"]
}
```

---

## Deliverables

| File | Description |
|------|-------------|
| `auto_alert_recovery_workflow.json` | Full workflow definition — POST to `/api/metadata/workflow` |
| `alert_ingestion_taskdef.json` | TaskDef for the ingestion worker |
| `execute_action_taskdef.json` | TaskDef for the execution worker |

---

## Verification Steps

1. Register task defs: `POST /api/metadata/taskdefs` with each TaskDef JSON
2. Register workflow: `POST /api/metadata/workflow` with the workflow JSON
3. Start a LOW-risk test run: `POST /api/workflow/execute/auto_alert_recovery/1` with a sample alert → confirm `ai_auto_execute` branch runs through to `verification`
4. Start a HIGH-risk test run → confirm workflow pauses at the `human_review` HUMAN task
5. Complete the HUMAN task: `POST /api/tasks/{taskId}` with an approved plan → confirm `execute_action` and `verification` proceed
