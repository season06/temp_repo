# Mock Scenario: "Deployment Not Ready" — Critical Alert

## Overview

| Field | Value |
|---|---|
| Alert source | AlertManager (Prometheus) |
| Alert name | KubeDeploymentReplicasMismatch |
| Severity | critical |
| Runbook action | `kubectl rollout restart` |
| Risk level | HIGH → human review required |
| Execution | kubectl via `execute_action` worker |

---

## Step 1 — `alert_ingestion` (SIMPLE worker)

**Input from AlertManager:**
```json
{
  "alert_id": "ALT-2026-0511-042",
  "alert_source": "alertmanager",
  "alert_severity": "critical",
  "alert_timestamp": "2026-05-11T14:32:00Z",
  "alert_payload": {
    "alertname": "KubeDeploymentReplicasMismatch",
    "namespace": "production",
    "deployment": "payment-service",
    "available_replicas": 0,
    "desired_replicas": 3,
    "severity": "critical",
    "message": "Deployment production/payment-service has 0/3 replicas available"
  }
}
```

**Worker output (normalized):**
```json
{
  "alert_id": "ALT-2026-0511-042",
  "source": "alertmanager",
  "alert_severity": "critical",
  "normalized_payload": {
    "alertname": "KubeDeploymentReplicasMismatch",
    "namespace": "production",
    "deployment": "payment-service",
    "available": 0,
    "desired": 3
  }
}
```

---

## Step 2 — `analyze_alert` (LLM_CHAT_COMPLETE)

**LLM output:**
```json
{
  "alert_type": "KubeDeploymentReplicasMismatch",
  "affected_service": "payment-service (namespace: production)",
  "potential_root_cause": "Pod crash loop, OOMKill, or image pull failure causing all replicas to be unavailable",
  "urgency": "critical",
  "summary": "All pods in production/payment-service deployment are down — 0 of 3 replicas available"
}
```

---

## Step 3 — `doc_search` (LLM_SEARCH_INDEX → pgvector)

Vector DB query: *"All pods in production/payment-service deployment are down"*

**Retrieved runbook chunk:**
```
Runbook: KubeDeploymentReplicasMismatch
Symptom: Deployment has 0 available replicas.
Resolution:
  1. Check pod logs: kubectl logs -n <namespace> -l app=<deployment> --previous
  2. Describe the failing pod: kubectl describe pod -n <namespace>
  3. If CrashLoopBackOff or OOMKilled: kubectl rollout restart deployment/<name> -n <namespace>
  4. If ImagePullBackOff: fix image tag and re-deploy.
```

---

## Step 4 — `investigation` (LLM_CHAT_COMPLETE)

**LLM output:**
```json
{
  "root_cause": "payment-service pods are crash-looping, likely due to OOMKill or a bad config introduced in the last rollout",
  "confidence_score": 0.82,
  "recommended_actions": [
    "kubectl rollout restart deployment/payment-service -n production",
    "kubectl rollout undo deployment/payment-service -n production"
  ],
  "estimated_impact": "Payment service is fully unavailable — all transactions failing",
  "affected_systems": ["payment-service", "order-service", "checkout-flow"]
}
```

---

## Step 5 — `risk_assessment` (LLM_CHAT_COMPLETE)

**LLM output:**
```json
{
  "risk_level": "HIGH",
  "risk_reason": "Restarting pods in production for a payment-critical service causes a brief but real outage window; if the crash persists post-restart, the situation worsens. Irreversible in the sense that in-flight transactions may be dropped.",
  "auto_executable": false,
  "requires_human_approval": true
}
```

---

## Step 6 — `decision_router` (SWITCH)

Expression evaluates `risk_level = "HIGH"` → returns `"HUMAN_REVIEW"`.

Workflow routes to `human_review`.

---

## Step 7 — `human_review` (HUMAN task — workflow pauses)

**What the operator sees in the Conductor UI:**
```
Alert:       ALT-2026-0511-042 — KubeDeploymentReplicasMismatch
Risk Level:  HIGH
Risk Reason: Restarting production pods may drop in-flight payment transactions
Root Cause:  payment-service pods crash-looping (likely OOMKill or bad rollout)
Actions:
  [1] kubectl rollout restart deployment/payment-service -n production
  [2] kubectl rollout undo deployment/payment-service -n production
Affected:    payment-service, order-service, checkout-flow
```

**Operator approves action [1] and completes the HUMAN task:**
```json
{
  "approved": true,
  "selected_action": "kubectl rollout restart deployment/payment-service -n production",
  "approved_by": "oncall-engineer@company.com",
  "approval_note": "Verified no active transactions in the last 30s, safe to restart"
}
```

---

## Step 8 — `execute_action` (SIMPLE worker)

The worker runs the approved kubectl command:

```bash
kubectl rollout restart deployment/payment-service -n production
```

Then polls for completion:
```bash
kubectl rollout status deployment/payment-service -n production --timeout=120s
```

**Worker output:**
```json
{
  "action_taken": "kubectl rollout restart deployment/payment-service -n production",
  "execution_result": "Waiting for deployment rollout to finish: 0 of 3 updated replicas are available... 3 of 3 updated replicas are available. Rollout complete.",
  "execution_timestamp": "2026-05-11T14:38:15Z"
}
```

---

## Step 9 — `verification` (LLM_CHAT_COMPLETE)

**LLM output:**
```json
{
  "status": "RESOLVED",
  "confidence_score": 0.96,
  "summary": "All 3 replicas of payment-service are now available after the restart. The deployment is healthy.",
  "next_steps": []
}
```

---

## What Needs to Be Built

| Component | Description |
|---|---|
| `alert_ingestion` worker | Polls Conductor task queue, normalizes AlertManager webhook payload, outputs `normalized_payload` |
| Vector DB seeding | Index runbook text into `pgvector-local`, namespace `runbooks`, index `incidents` |
| `execute_action` worker | Receives `selected_action` string, runs `kubectl` (needs kubeconfig or in-cluster ServiceAccount), streams rollout status back as `execution_result` |
| Conductor HUMAN task UI | Built-in — operator approves via the Conductor UI or completes the task via `POST /api/tasks/{taskId}` |

The only bespoke code is the two SIMPLE workers and the runbook indexing. Everything else — LLM analysis, risk routing, human gate, verification — is handled natively by the workflow engine.
