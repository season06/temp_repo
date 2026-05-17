# seed_runbooks — Workflow Documentation

## Purpose

`seed_runbooks` indexes SRE runbook documents into the pgvector store. Each run indexes one document. The `doc_search` task in `auto_alert_recovery` queries this same store to retrieve relevant remediation guidance at runtime.

## Workflow Definition

File: `seed_runbooks_workflow.json`
Register: `POST /api/metadata/workflow`

```
index_runbook (LLM_INDEX_TEXT)
```

One task — embed `runbook_text` via the configured embedding model and write it to the vector DB under the given `namespace` / `index` / `runbook_id`.

---

## Input Parameters

| Parameter          | Type   | Description |
|--------------------|--------|-------------|
| `llm_provider`     | string | LLM provider to use for embeddings (e.g. `openai`) |
| `embedding_model`  | string | Embedding model name (e.g. `text-embedding-3-small`) |
| `vector_db_provider` | string | Registered vector DB name (e.g. `pgvector-local`) |
| `vector_db_namespace` | string | Logical grouping, like a schema (e.g. `runbooks`) |
| `vector_db_index`  | string | Table/collection name within the namespace (e.g. `incidents`) |
| `runbook_text`     | string | Full text of the runbook to index |
| `runbook_id`       | string | Unique document ID (used for deduplication / upsert) |

---

## Examples

### Example 1 — KubeDeploymentReplicasMismatch

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
      "runbook_id": "runbook_kube_deployment_mismatch",
      "runbook_text": "Runbook: KubeDeploymentReplicasMismatch\nSymptom: Deployment has 0 available replicas.\nResolution:\n  1. Check pod logs: kubectl logs -n <namespace> -l app=<deployment> --previous\n  2. Describe the failing pod: kubectl describe pod -n <namespace>\n  3. If CrashLoopBackOff or OOMKilled: kubectl rollout restart deployment/<name> -n <namespace>\n  4. If ImagePullBackOff: fix image tag and re-deploy.\nRisk: HIGH - restarting production pods may drop in-flight requests."
    }
  }'
```

### Example 2 — HighCPUUsage

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
      "runbook_id": "runbook_high_cpu_usage",
      "runbook_text": "Runbook: HighCPUUsage\nSymptom: CPU usage above 90% for more than 5 minutes on one or more instances.\nResolution:\n  1. Identify top processes: kubectl exec -n <namespace> <pod> -- top\n  2. Check for traffic spike: review ingress metrics in Grafana.\n  3. If traffic spike: scale out the deployment: kubectl scale deployment/<name> --replicas=<n> -n <namespace>\n  4. If rogue process: kubectl delete pod <pod> -n <namespace> to trigger a clean restart.\n  5. If persistent: review recent deployments for a regression: kubectl rollout history deployment/<name> -n <namespace>\nRisk: MEDIUM - scaling out is safe; deleting a pod causes brief disruption."
    }
  }'
```

### Example 3 — PodOOMKilled

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
      "runbook_id": "runbook_pod_oomkilled",
      "runbook_text": "Runbook: PodOOMKilled\nSymptom: Pod terminated with reason OOMKilled; container exceeded its memory limit.\nResolution:\n  1. Check current memory limits: kubectl describe pod <pod> -n <namespace>\n  2. Short-term: increase the memory limit in the deployment manifest and apply: kubectl set resources deployment/<name> --limits=memory=<value> -n <namespace>\n  3. Trigger a rolling restart to pick up new limits: kubectl rollout restart deployment/<name> -n <namespace>\n  4. Long-term: profile the application for memory leaks.\nRisk: HIGH - changing resource limits in production requires care; rolling restart causes brief pod churn."
    }
  }'
```

---

## Seeding Multiple Runbooks

To seed all runbooks at once, run the curl commands sequentially or in parallel:

```bash
# Seed all three in parallel
curl -s -X POST ... &   # KubeDeploymentReplicasMismatch
curl -s -X POST ... &   # HighCPUUsage
curl -s -X POST ... &   # PodOOMKilled
wait
```

---

## How It Connects to `auto_alert_recovery`

```
seed_runbooks (run once per runbook)
    └─ LLM_INDEX_TEXT → pgvector-local / runbooks / incidents

auto_alert_recovery (runs per alert)
    └─ doc_search (LLM_SEARCH_INDEX) → queries pgvector-local / runbooks / incidents
         └─ returns top-5 matching runbook chunks → feeds investigation task
```

The `doc_search` query is the alert summary produced by `analyze_alert`. The closer your runbook text matches the alert language, the higher the retrieval score.

---

## Updating a Runbook

Re-run `seed_runbooks` with the same `runbook_id` — the vector DB will upsert the document in place.
