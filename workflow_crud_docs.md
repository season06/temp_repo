# Conductor Workflow — Create / Update / Execute

Base URL: `http://localhost:8000`

---

## 1. Create a workflow definition

Registers a new workflow. Fails if a workflow with the same `name` + `version` already exists.

```
POST /api/metadata/workflow
Content-Type: application/json
```

**Body** — a single `WorkflowDef` object:

```json
{
  "name": "my_workflow",
  "version": 1,
  "schemaVersion": 2,
  "tasks": [
    {
      "name": "my_task",
      "taskReferenceName": "my_task_ref",
      "type": "SIMPLE",
      "inputParameters": {
        "key": "${workflow.input.key}"
      }
    }
  ],
  "inputParameters": ["key"],
  "outputParameters": {
    "result": "${my_task_ref.output.result}"
  }
}
```

**Response** — `200 OK` (no body on success).

```bash
curl -X POST http://localhost:8000/api/metadata/workflow \
  -H "Content-Type: application/json" \
  -d @./workflow_2/dynamic_agent_planner.json
```

---

## 2. Update a workflow definition

Creates or updates one or more workflow definitions. Safe to call even if the workflow already exists.

```
PUT /api/metadata/workflow
Content-Type: application/json
```

**Body** — an **array** of `WorkflowDef` objects (even for a single workflow):

```bash
curl -X PUT http://localhost:8000/api/metadata/workflow \
  -H "Content-Type: application/json" \
  -d "[$(cat my_workflow.json)]"
```

**Response** — bulk result with any errors:

```json
{
  "bulkErrorResults": {},
  "bulkSuccessfulResults": ["my_workflow"]
}
```

> Use `PUT` for day-to-day updates. Use `POST` only for the very first registration.

---

## 3. Get a workflow definition

```
GET /api/metadata/workflow/{name}?version={version}
```

`version` is optional — omitting it returns the latest version.

```bash
curl http://localhost:8000/api/metadata/workflow/my_workflow
curl http://localhost:8000/api/metadata/workflow/my_workflow?version=2
```

List all workflow definitions:

```bash
curl http://localhost:8000/api/metadata/workflow
```

List names and versions only (lightweight):

```bash
curl http://localhost:8000/api/metadata/workflow/names-and-versions
```

---

## 4. Delete a workflow definition

Removes the definition only. Does **not** affect running or completed workflow instances.

```
DELETE /api/metadata/workflow/{name}/{version}
```

```bash
curl -X DELETE http://localhost:8000/api/metadata/workflow/my_workflow/1
```

---

## 5. Execute a workflow (async)

Starts a workflow and returns its instance ID immediately.

```
POST /api/workflow/{name}?version={version}&correlationId={id}&priority={0-99}
Content-Type: application/json
```

**Body** — the workflow input as a plain JSON object:

```bash
curl -X POST "http://localhost:8000/api/workflow/my_workflow?version=1" \
  -H "Content-Type: application/json" \
  -d '{"role": "user"}'
```

**Response** — the workflow instance ID (plain text):

```
a1b2c3d4-0000-0000-0000-000000000000
```

Track it later:

```bash
curl http://localhost:8000/api/workflow/a1b2c3d4-0000-0000-0000-000000000000
```

### Example: `dynamic_agent_planner`                                                                                   
                                                                                                                       
This workflow takes a natural-language task, uses an LLM (GPT-4o) to generate a Conductor workflow definition, waits for human approval, then executes the generated workflow.

**Input parameters:**

| Field | Type | Description |
|---|---|---|
| `task` | string | Natural-language description of what the generated workflow should do |
| `taskInput` | object | Input passed into the dynamically generated sub-workflow |

**Output parameters:**

| Field | Description |
|---|---|
| `generatedPlan` | The workflow definition JSON produced by the LLM |
| `executionId` | Workflow instance ID of the executed sub-workflow |

```bash                                                                                                                
curl -X POST "http://localhost:8000/api/workflow/dynamic_agent_planner?version=1" \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Fetch the latest news headlines and summarize them into bullet points",
    "taskInput": {
      "topic": "AI"
    }
  }'
```                                                                                                                    

---

## 6. Execute a workflow (sync — wait for result)

Starts the workflow and waits up to `waitForSeconds` for it to complete or reach a specific task.

```
POST /api/workflow/execute/{name}/{version}
Content-Type: application/json
```

Query params:

| Param | Default | Description |
|---|---|---|
| `requestId` | random UUID | Idempotency key |
| `waitUntilTaskRef` | — | Comma-separated task reference names to stop waiting at |
| `waitForSeconds` | `10` | Max seconds to wait before returning current state |
| `consistency` | `DURABLE` | `DURABLE` or `EVENTUAL` |
| `returnStrategy` | `TARGET_WORKFLOW` | What to include in the response |

```bash
curl -X POST "http://localhost:8000/api/workflow/execute/my_workflow/1?waitForSeconds=30" \
  -H "Content-Type: application/json" \
  -d '{"name": "my_workflow", "input": {"key": "hello"}}'
```

**Response** — `SignalResponse` JSON with workflow status and output.

---

## 7. Execute with full StartWorkflowRequest

Use this when you need additional options (task-to-domain mapping, inline workflow definition, priority, etc.).

```
POST /api/workflow
Content-Type: application/json
```

```json
{
  "name": "my_workflow",
  "version": 1,
  "correlationId": "optional-trace-id",
  "priority": 0,
  "input": {
    "key": "hello"
  },
  "taskToDomain": {
    "my_task": "prod"
  }
}
```

```bash
curl -X POST http://localhost:8000/api/workflow \
  -H "Content-Type: application/json" \
  -d '{"name":"my_workflow","version":1,"input":{"key":"hello"}}'
```

**Response** — workflow instance ID (plain text).

---

## Quick reference

| Action | Method | Path |
|---|---|---|
| Create definition | `POST` | `/api/metadata/workflow` |
| Create or update definition(s) | `PUT` | `/api/metadata/workflow` |
| Get definition | `GET` | `/api/metadata/workflow/{name}` |
| List all definitions | `GET` | `/api/metadata/workflow` |
| Delete definition | `DELETE` | `/api/metadata/workflow/{name}/{version}` |
| Start workflow (async) | `POST` | `/api/workflow/{name}` |
| Start workflow (full options) | `POST` | `/api/workflow` |
| Start workflow (sync/wait) | `POST` | `/api/workflow/execute/{name}/{version}` |
| Get workflow instance | `GET` | `/api/workflow/{workflowId}` |
| Retry failed workflow | `POST` | `/api/workflow/{workflowId}/retry` |
| Pause workflow | `PUT` | `/api/workflow/{workflowId}/pause` |
| Resume workflow | `PUT` | `/api/workflow/{workflowId}/resume` |
| Restart workflow | `POST` | `/api/workflow/{workflowId}/restart` |
| Terminate workflow | `DELETE` | `/api/workflow/{workflowId}` |
