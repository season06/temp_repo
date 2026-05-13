#!/usr/bin/env python3
"""
execute_action worker

Polls Conductor for `execute_action` tasks and runs docker restart commands.
Only `docker restart <container>` is permitted — all other commands are rejected.

Usage:
    python3 execute_action_worker.py

Requirements:
    pip install requests
"""

import json
import re
import subprocess
import time

import requests

CONDUCTOR_URL = "http://localhost:8000"
TASK_TYPE = "execute_action"
WORKER_ID = "execute-action-worker-01"
POLL_INTERVAL = 2  # seconds


def poll() -> dict | None:
    try:
        r = requests.get(
            f"{CONDUCTOR_URL}/api/tasks/poll/{TASK_TYPE}?workerid={WORKER_ID}",
            timeout=5,
        )
        if r.status_code == 200 and r.text.strip():
            return r.json()
    except requests.RequestException as e:
        print(f"[poll] error: {e}")
    return None


def complete(task_id: str, workflow_id: str, status: str, output: dict):
    try:
        requests.post(
            f"{CONDUCTOR_URL}/api/tasks",
            json={
                "taskId": task_id,
                "workflowInstanceId": workflow_id,
                "status": status,
                "outputData": output,
            },
            timeout=10,
        )
    except requests.RequestException as e:
        print(f"[complete] error: {e}")


def extract_command(action_plan) -> str:
    """Pull selected_action out of the action plan (dict or JSON string)."""
    if isinstance(action_plan, str):
        try:
            action_plan = json.loads(action_plan)
        except json.JSONDecodeError:
            return action_plan.strip()

    if isinstance(action_plan, dict):
        # HUMAN task output or ai_auto_execute output
        return (
            action_plan.get("selected_action")
            or action_plan.get("outputData", {}).get("selected_action", "")
        )

    return ""


def validate(cmd: str) -> tuple[bool, str]:
    """Allow only: docker restart <container-name>"""
    cmd = cmd.strip()
    if re.fullmatch(r"docker restart [\w.\-]+", cmd):
        return True, cmd
    return False, f"Rejected: only 'docker restart <container>' is allowed. Got: {cmd!r}"


def run(cmd: str) -> tuple[int, str, str]:
    result = subprocess.run(cmd.split(), capture_output=True, text=True, timeout=30)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def container_status(name: str) -> str:
    code, out, _ = run(f"docker inspect --format {{{{.State.Status}}}} {name}")
    return out if code == 0 else "unknown"


def process(task: dict):
    task_id = task["taskId"]
    workflow_id = task["workflowInstanceId"]
    action_plan = task.get("inputData", {}).get("action_plan", {})

    print(f"\n[{task_id[:8]}] received task")
    print(f"[{task_id[:8]}] action_plan: {str(action_plan)[:200]}")

    cmd = extract_command(action_plan)
    if not cmd:
        print(f"[{task_id[:8]}] no command found")
        complete(task_id, workflow_id, "FAILED", {"error": "No selected_action in action_plan"})
        return

    ok, msg = validate(cmd)
    if not ok:
        print(f"[{task_id[:8]}] {msg}")
        complete(task_id, workflow_id, "FAILED", {"error": msg})
        return

    container = cmd.split()[-1]
    print(f"[{task_id[:8]}] executing: {cmd}")

    code, stdout, stderr = run(cmd)
    output_text = stdout if code == 0 else stderr

    time.sleep(2)  # let the container stabilize
    status_after = container_status(container)

    success = code == 0 and status_after == "running"
    task_status = "COMPLETED" if success else "FAILED"

    output = {
        "action_taken": cmd,
        "execution_result": output_text or f"exit code {code}",
        "exit_code": code,
        "container_name": container,
        "container_status_after": status_after,
        "success": success,
    }

    complete(task_id, workflow_id, task_status, output)
    print(f"[{task_id[:8]}] done — status={task_status}, container={status_after}")


def main():
    print(f"execute_action worker ready")
    print(f"  Conductor : {CONDUCTOR_URL}")
    print(f"  Task type : {TASK_TYPE}")
    print(f"  Worker ID : {WORKER_ID}")
    print(f"  Allowed   : docker restart <container>")
    print()

    while True:
        try:
            task = poll()
            if task:
                process(task)
            else:
                time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            print("\nWorker stopped.")
            break
        except Exception as e:
            print(f"[error] {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
