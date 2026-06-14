# Azure Flow Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the end-to-end flow from finding an Azure release definition to triggering its tasks, and wire `main.py` into `monitor.py`'s orchestrator through an injected API seam.

**Architecture:** `monitor.py` becomes a reusable library whose `ReleaseRunner`/polling go through an injected `api` object (two methods: `trigger_task`, `get_task_info`). `monitor.py` ships a `MockApi` (over `mock_api.json`); `main.py` ships an `AzureApi` plus the real Azure REST request shapes (with the single network call left as a `NotImplementedError` stub) and the interactive CLI flow.

**Tech Stack:** Python 3.11+ stdlib only (`asyncio`, `argparse`, `base64`, `unittest`). No third-party deps.

**Spec:** `docs/superpowers/specs/2026-06-05-azure-flow-integration-design.md`

---

## File Structure

- `monitor.py` (modify) — add `MockApi`, `run_orchestration`; thread `api` through `ReleaseRunner.run`, `_wait_chain_terminal`, `_poll_chain`, `poll_task`, `fetch_task_update`; rewrite `monitor()`.
- `test_monitor.py` (modify) — add `FakeApi`; update poll/run/chain tests to the injected-`api` interface.
- `main.py` (rewrite) — constants, Azure REST layer (`_basic_auth`, `_send_request`, `find_release_definition`, `create_release`, `get_release`, `trigger_release_task`), `parse_selection`, `_prompt_selection`, `AzureApi`, `main()`.
- `test_main.py` (create) — request shaping, fuzzy filter, selection parsing, `AzureApi` mapping, `main()` smoke test.

---

## Task 1: Refactor monitor.py to the injected API seam

**Files:**
- Modify: `monitor.py`
- Test: `test_monitor.py`

- [ ] **Step 1: Add `FakeApi` and rewrite the affected tests in `test_monitor.py`**

Add this class near the top of `test_monitor.py` (after the imports, before the first test class):

```python
class FakeApi:
    """Test double for the monitor API seam.

    responses: dict mapping task_id -> response dict, or task_id -> callable(task_id)->dict.
    trigger_errors: task ids whose trigger_task should raise.
    """
    def __init__(self, responses=None, trigger_errors=None):
        self.responses = responses or {}
        self.trigger_errors = set(trigger_errors or [])
        self.trigger_order = []

    async def trigger_task(self, release_id, task_id):
        self.trigger_order.append(task_id)
        if task_id in self.trigger_errors:
            raise ConnectionError("simulated")

    async def get_task_info(self, release_id, task_id, task_name):
        r = self.responses[task_id]
        return r(task_id) if callable(r) else r
```

Replace `test_fetch_task_update_returns_error_on_failure` with:

```python
    async def test_fetch_task_update_returns_error_on_failure(self):
        update = await monitor.fetch_task_update(monitor.MockApi(), 1, 999, "task-x")
        self.assertEqual(update.status, "Error")
        self.assertIsNone(update.dependency_id)
```

Replace the three `PollTaskAsyncTests` methods with:

```python
    async def test_poll_task_updates_in_place(self):
        task = monitor.Task(id=101, name="task-a")
        api = FakeApi({101: {"status": "InProgress",
                             "dependency_task_id": 102,
                             "dependency_task_name": "task-b"}})

        new_dep = await monitor.poll_task(task, 1, api)

        self.assertEqual(task.status, "InProgress")
        self.assertEqual(task.dependency_id, 102)
        self.assertIsNotNone(new_dep)
        self.assertEqual(new_dep.id, 102)
        self.assertEqual(new_dep.name, "task-b")

    async def test_poll_task_skips_when_terminal(self):
        task = monitor.Task(id=101, name="task-a", status="Successed")

        def boom(_):
            raise AssertionError("should not be called")

        api = FakeApi({101: boom})
        result = await monitor.poll_task(task, 1, api)

        self.assertIsNone(result)

    async def test_poll_task_returns_none_when_no_dep(self):
        task = monitor.Task(id=102, name="task-b")
        api = FakeApi({102: {"status": "InProgress",
                             "dependency_task_id": None,
                             "dependency_task_name": None}})

        result = await monitor.poll_task(task, 1, api)

        self.assertIsNone(result)
```

Replace `PollChainTests.test_poll_chain_discovers_dependency` with:

```python
    async def test_poll_chain_discovers_dependency(self):
        runner = self._runner()
        tasks = {101: monitor.Task(id=101, name="task-a")}
        api = FakeApi({
            101: {"status": "InProgress", "dependency_task_id": 102, "dependency_task_name": "task-b"},
            102: {"status": "NotStarted", "dependency_task_id": None, "dependency_task_name": None},
        })

        await runner._poll_chain(101, tasks, api)

        self.assertIn(102, tasks)
        self.assertEqual(tasks[102].name, "task-b")
        self.assertEqual(tasks[101].status, "InProgress")
        self.assertEqual(tasks[102].status, "NotStarted")
```

Replace the four `ReleaseRunnerRunTests` methods with:

```python
    async def test_run_triggers_queue_sequentially(self):
        """trigger order must be [101, 201]; 201 not triggered until 101+cascade terminal."""
        runner = monitor.ReleaseRunner.from_input(
            "release-1", ["task-a", "task-c"], [self._release()],
        )
        tasks = {}
        api = FakeApi({
            101: {"status": "Successed", "dependency_task_id": 102, "dependency_task_name": "task-b"},
            102: {"status": "Successed", "dependency_task_id": None, "dependency_task_name": None},
            201: {"status": "Successed", "dependency_task_id": None, "dependency_task_name": None},
        })

        await runner.run(tasks, api)

        self.assertEqual(api.trigger_order, [101, 201])
        self.assertTrue(runner.is_done())
        self.assertEqual(runner.triggered, [101, 201])
        self.assertIsNone(runner.active_root_id)

    async def test_run_waits_for_cascade_before_advancing(self):
        """task-c is not triggered until task-a AND task-b reach terminal."""
        runner = monitor.ReleaseRunner.from_input(
            "release-1", ["task-a", "task-c"], [self._release()],
        )
        tasks = {}
        poll_count = {101: 0, 102: 0, 201: 0}

        def responder(task_id):
            poll_count[task_id] += 1
            if task_id == 101:
                return {"status": "Successed", "dependency_task_id": 102, "dependency_task_name": "task-b"}
            if task_id == 102:
                return {"status": "InProgress"} if poll_count[102] < 3 else {"status": "Successed"}
            return {"status": "Successed"}

        api = FakeApi({101: responder, 102: responder, 201: responder})

        async def no_sleep(_):
            return

        with patch.object(monitor.asyncio, "sleep", side_effect=no_sleep):
            await runner.run(tasks, api)

        self.assertEqual(api.trigger_order, [101, 201])
        self.assertGreaterEqual(poll_count[102], 3)

    async def test_run_continues_after_trigger_failure(self):
        """trigger_task raises for 101 -> task is marked Error, run() advances to 201."""
        runner = monitor.ReleaseRunner.from_input(
            "release-1", ["task-a", "task-c"], [self._release()],
        )
        tasks = {}
        api = FakeApi(
            responses={201: {"status": "Successed"}},
            trigger_errors={101},
        )

        await runner.run(tasks, api)

        self.assertEqual(api.trigger_order, [101, 201])
        self.assertEqual(tasks[101].status, "Error")
        self.assertTrue(runner.is_done())

    async def test_run_continues_after_task_failure(self):
        """task-a returns Failed (terminal) -> 201 still triggered."""
        runner = monitor.ReleaseRunner.from_input(
            "release-1", ["task-a", "task-c"], [self._release()],
        )
        tasks = {}

        def responder(task_id):
            return {"status": "Failed"} if task_id == 101 else {"status": "Successed"}

        api = FakeApi({101: responder, 201: responder})

        await runner.run(tasks, api)

        self.assertEqual(api.trigger_order, [101, 201])
        self.assertEqual(tasks[101].status, "Failed")
```

- [ ] **Step 2: Run the tests to confirm they fail against the old interface**

Run: `python -m pytest test_monitor.py -q`
Expected: FAIL (e.g. `AttributeError: module 'monitor' has no attribute 'MockApi'`, and `TypeError` for `poll_task`/`run` arity).

- [ ] **Step 3: Refactor `monitor.py` — thread `api` through the runner and polling**

Replace `ReleaseRunner.run` with:

```python
    async def run(self, tasks: dict, api) -> None:
        """Walk the trigger queue. Trigger each task and wait for its chain to terminate
        before moving on. Trigger failures mark the task Error and advance."""
        for name in self.trigger_queue:
            tid = self._resolve_name(name)
            self.active_root_id = tid
            self.triggered.append(tid)
            tasks[tid] = Task(id=tid, name=name)

            try:
                await api.trigger_task(self.release.id, tid)
            except Exception:
                tasks[tid].status = "Error"
                self.active_root_id = None
                continue

            await self._wait_chain_terminal(tid, tasks, api)
            self.active_root_id = None

        self._done = True
```

Replace `ReleaseRunner._wait_chain_terminal` with:

```python
    async def _wait_chain_terminal(self, root_id: int, tasks: dict, api) -> None:
        """Poll-and-wait until root's chain is fully terminal."""
        while True:
            await self._poll_chain(root_id, tasks, api)
            if chain_terminal(root_id, tasks):
                return
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
```

Replace `ReleaseRunner._poll_chain` with:

```python
    async def _poll_chain(self, root_id: int, tasks: dict, api) -> None:
        """Poll root + all known cascade tasks once. Newly discovered deps join `tasks`."""
        worklist = [tasks[root_id]]
        seen = set()
        while worklist:
            task = worklist.pop()
            if task.id in seen:
                continue
            seen.add(task.id)

            new_dep = await poll_task(task, self.release.id, api)
            if new_dep and new_dep.id not in tasks:
                tasks[new_dep.id] = new_dep
                worklist.append(new_dep)
            elif task.dependency_id and task.dependency_id in tasks:
                worklist.append(tasks[task.dependency_id])
```

Replace `poll_task` with:

```python
async def poll_task(task, release_id, api):
    """Apply the latest update to a task. Return the newly discovered dependency, if any."""
    if is_terminate_status(task.status):
        return None

    update = await fetch_task_update(api, release_id, task.id, task.name)
    task.status = update.status
    task.dependency_id = update.dependency_id
    task.dependency_name = update.dependency_name

    if update.dependency_id and update.dependency_name:
        return Task(id=update.dependency_id, name=update.dependency_name)

    return None
```

Replace `fetch_task_update` with:

```python
async def fetch_task_update(api, release_id, task_id, task_name) -> TaskUpdate:
    """Fetch latest task state via the API seam. Return an Error update if the call fails."""
    try:
        info = await api.get_task_info(release_id, task_id, task_name)
    except Exception:
        return TaskUpdate(status="Error")
    return TaskUpdate(
        status=info.get("status", "Unknown"),
        dependency_id=info.get("dependency_task_id"),
        dependency_name=info.get("dependency_task_name"),
    )
```

- [ ] **Step 4: Add `MockApi` and `run_orchestration`, and rewrite `monitor()`**

Add `MockApi` immediately after the `trigger_task` mock function (the mock helpers `get_release_metadata`, `get_release_task_info`, `trigger_task` stay):

```python
class MockApi:
    """Default API seam backed by mock_api.json. Swap with AzureApi (main.py) in prod."""

    async def trigger_task(self, release_id, task_id) -> None:
        await trigger_task(task_id)

    async def get_task_info(self, release_id, task_id, task_name) -> dict:
        return await get_release_task_info(release_id, task_id, task_name)
```

Add `run_orchestration` just above `monitor()`:

```python
async def run_orchestration(runners: list, tasks: dict, api, writer) -> None:
    """Run every release's runner concurrently with the render heartbeat."""
    await asyncio.gather(
        *(r.run(tasks, api) for r in runners),
        render_loop(runners, tasks, writer),
    )
```

Replace `monitor()` with:

```python
async def monitor() -> None:
    """Run the trigger-and-monitor loop until every release's queue is drained."""
    be_trigger_release: list = [
        ("release-1", ["task-a", "task-c"]),
    ]

    releases = await get_release_metadata()
    runners = [
        ReleaseRunner.from_input(release_name, task_names, releases)
        for release_name, task_names in be_trigger_release
    ]

    tasks: dict = {}
    writer = LiveWriter()
    api = MockApi()
    print("===Start===")

    try:
        await run_orchestration(runners, tasks, api, writer)
    except KeyboardInterrupt:
        print("\n===Cancelled===")
```

- [ ] **Step 5: Run the full monitor suite to verify it passes**

Run: `python -m pytest test_monitor.py -q`
Expected: PASS (all tests green).

- [ ] **Step 6: Commit**

```bash
git add monitor.py test_monitor.py
git commit -m "refactor: inject API seam into monitor; add MockApi + run_orchestration"
```

---

## Task 2: main.py scaffolding — constants, basic auth, single HTTP stub

**Files:**
- Modify: `main.py` (replace the file's contents incrementally; this task adds the top section)
- Test: `test_main.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `test_main.py`:

```python
import base64
import sys
import unittest
from unittest.mock import patch

import main


class AuthAndTransportTests(unittest.TestCase):
    def test_basic_auth_encodes_pat_with_leading_colon(self):
        expected = "Basic " + base64.b64encode(b":abc").decode()
        self.assertEqual(main._basic_auth("abc"), expected)

    def test_send_request_is_unimplemented_stub(self):
        with self.assertRaises(NotImplementedError):
            main._send_request("GET", "https://example/x", "PAT")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest test_main.py -q`
Expected: FAIL (`ModuleNotFoundError`/`AttributeError`: `_basic_auth`/`_send_request` not defined).

- [ ] **Step 3: Write the top of `main.py`**

Replace the entire contents of `main.py` with this scaffolding (later tasks append functions below the marked sections):

```python
import argparse
import asyncio
import base64

from monitor import (
    LiveWriter,
    Release,
    ReleaseRunner,
    ReleaseTaskDef,
    run_orchestration,
)

# ========= Config =========

ORG = "my-org"
PROJECT = "my-project"
API_VERSION = "7.1"
RELEASE_HOST = f"https://vsrm.dev.azure.com/{ORG}/{PROJECT}/_apis/release"


# ========= Azure API transport =========

def _basic_auth(pat: str) -> str:
    """Build the Azure DevOps PAT basic-auth header value."""
    token = base64.b64encode(b":" + pat.encode()).decode()
    return f"Basic {token}"


def _send_request(method, url, pat, body=None) -> dict:
    """The ONE network call. Builds the auth header for real; the actual HTTP
    send is the single fill-in point for prod (e.g. requests.request / urllib)."""
    headers = {"Authorization": _basic_auth(pat), "Content-Type": "application/json"}
    _ = (method, url, headers, body)
    raise NotImplementedError("wire real HTTP here (e.g. requests.request / urllib)")
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest test_main.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add main.py test_main.py
git commit -m "feat: main.py scaffolding with PAT auth and single HTTP stub"
```

---

## Task 3: find_release_definition

**Files:**
- Modify: `main.py`
- Test: `test_main.py`

- [ ] **Step 1: Write the failing test**

Add to `test_main.py`:

```python
class AzureRequestShapingTests(unittest.TestCase):
    def test_find_release_definition_shapes_request_and_fuzzy_filters(self):
        captured = {}

        def fake_send(method, url, pat, body=None):
            captured.update(method=method, url=url, pat=pat, body=body)
            return {"value": [
                {"id": 10, "name": "Deploy-App"},
                {"id": 11, "name": "Build-Lib"},
            ]}

        with patch.object(main, "_send_request", side_effect=fake_send):
            result = main.find_release_definition("PAT", "app")

        self.assertEqual(captured["method"], "GET")
        self.assertIn("/definitions", captured["url"])
        self.assertIn("searchText=app", captured["url"])
        self.assertEqual(captured["pat"], "PAT")
        self.assertEqual(result, [("Deploy-App", 10)])
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest test_main.py::AzureRequestShapingTests::test_find_release_definition_shapes_request_and_fuzzy_filters -q`
Expected: FAIL (`AttributeError: ... has no attribute 'find_release_definition'`).

- [ ] **Step 3: Implement**

Append to `main.py` (under the transport section):

```python
def find_release_definition(pat, definition_name) -> list:
    """Find release definitions by name (case-insensitive substring fuzzy match).
    Returns a list of (name, id)."""
    url = f"{RELEASE_HOST}/definitions?searchText={definition_name}&api-version={API_VERSION}"
    data = _send_request("GET", url, pat)
    needle = definition_name.lower()
    return [
        (d["name"], d["id"])
        for d in data.get("value", [])
        if needle in d["name"].lower()
    ]
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest test_main.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add main.py test_main.py
git commit -m "feat: find_release_definition with fuzzy filter"
```

---

## Task 4: create_release

**Files:**
- Modify: `main.py`
- Test: `test_main.py`

- [ ] **Step 1: Write the failing test**

Add to `AzureRequestShapingTests`:

```python
    def test_create_release_posts_definition_id_and_returns_id(self):
        captured = {}

        def fake_send(method, url, pat, body=None):
            captured.update(method=method, url=url, body=body)
            return {"id": 500}

        with patch.object(main, "_send_request", side_effect=fake_send):
            release_id = main.create_release("PAT", 10)

        self.assertEqual(captured["method"], "POST")
        self.assertIn("/releases", captured["url"])
        self.assertEqual(captured["body"], {"definitionId": 10})
        self.assertEqual(release_id, 500)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest test_main.py -q`
Expected: FAIL (`AttributeError: create_release`).

- [ ] **Step 3: Implement**

Append to `main.py`:

```python
def create_release(pat, definition_id) -> int:
    """Create a new release from a definition. Returns the created release id."""
    url = f"{RELEASE_HOST}/releases?api-version={API_VERSION}"
    data = _send_request("POST", url, pat, {"definitionId": definition_id})
    return data["id"]
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest test_main.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add main.py test_main.py
git commit -m "feat: create_release"
```

---

## Task 5: get_release

**Files:**
- Modify: `main.py`
- Test: `test_main.py`

- [ ] **Step 1: Write the failing test**

Add to `AzureRequestShapingTests`:

```python
    def test_get_release_shapes_request_and_returns_payload(self):
        captured = {}
        payload = {"name": "Deploy-App", "environments": [{"id": 7, "name": "stage-1", "status": "notStarted"}]}

        def fake_send(method, url, pat, body=None):
            captured.update(method=method, url=url)
            return payload

        with patch.object(main, "_send_request", side_effect=fake_send):
            result = main.get_release("PAT", 500)

        self.assertEqual(captured["method"], "GET")
        self.assertIn("/releases/500", captured["url"])
        self.assertEqual(result, payload)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest test_main.py -q`
Expected: FAIL (`AttributeError: get_release`).

- [ ] **Step 3: Implement**

Append to `main.py`:

```python
def get_release(pat, release_id) -> dict:
    """Get release detail including environments. Returns the release JSON."""
    url = f"{RELEASE_HOST}/releases/{release_id}?api-version={API_VERSION}"
    return _send_request("GET", url, pat)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest test_main.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add main.py test_main.py
git commit -m "feat: get_release"
```

---

## Task 6: trigger_release_task

**Files:**
- Modify: `main.py`
- Test: `test_main.py`

- [ ] **Step 1: Write the failing test**

Add to `AzureRequestShapingTests`:

```python
    def test_trigger_release_task_patches_environment_to_inprogress(self):
        captured = {}

        def fake_send(method, url, pat, body=None):
            captured.update(method=method, url=url, body=body)
            return {"id": 7, "status": "inProgress"}

        with patch.object(main, "_send_request", side_effect=fake_send):
            result = main.trigger_release_task("PAT", 500, 7)

        self.assertEqual(captured["method"], "PATCH")
        self.assertIn("/releases/500/environments/7", captured["url"])
        self.assertEqual(captured["body"], {"status": "inProgress"})
        self.assertEqual(result["status"], "inProgress")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest test_main.py -q`
Expected: FAIL (`AttributeError: trigger_release_task`).

- [ ] **Step 3: Implement**

Append to `main.py`:

```python
def trigger_release_task(pat, release_id, environment_id) -> dict:
    """Trigger a release task by setting its environment status to inProgress.
    Returns the updated environment JSON."""
    url = f"{RELEASE_HOST}/releases/{release_id}/environments/{environment_id}?api-version={API_VERSION}"
    return _send_request("PATCH", url, pat, {"status": "inProgress"})
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest test_main.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add main.py test_main.py
git commit -m "feat: trigger_release_task"
```

---

## Task 7: parse_selection helper

**Files:**
- Modify: `main.py`
- Test: `test_main.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_main.py`:

```python
class ParseSelectionTests(unittest.TestCase):
    def test_parses_comma_separated_one_based_to_zero_based(self):
        self.assertEqual(main.parse_selection("1,3", 3), [0, 2])

    def test_strips_whitespace_and_ignores_empty_parts(self):
        self.assertEqual(main.parse_selection(" 2 , ", 3), [1])

    def test_rejects_empty(self):
        with self.assertRaises(ValueError):
            main.parse_selection("", 3)

    def test_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            main.parse_selection("9", 3)

    def test_rejects_non_numeric(self):
        with self.assertRaises(ValueError):
            main.parse_selection("x", 3)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest test_main.py::ParseSelectionTests -q`
Expected: FAIL (`AttributeError: parse_selection`).

- [ ] **Step 3: Implement**

Append to `main.py` (under an `# ========= Interactive helpers =========` comment):

```python
# ========= Interactive helpers =========

def parse_selection(raw, count) -> list:
    """Parse a '1,3' style 1-based selection into 0-based indices within [0, count).
    Raises ValueError on empty or out-of-range input."""
    indices = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        n = int(part)
        if not 1 <= n <= count:
            raise ValueError(f"selection out of range: {n}")
        indices.append(n - 1)
    if not indices:
        raise ValueError("no selection")
    return indices
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest test_main.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add main.py test_main.py
git commit -m "feat: parse_selection helper"
```

---

## Task 8: AzureApi seam adapter

**Files:**
- Modify: `main.py`
- Test: `test_main.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_main.py`:

```python
class AzureApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_task_info_maps_environment_status(self):
        def fake_get_release(pat, release_id):
            return {"name": "rel", "environments": [
                {"id": 5, "name": "stage-1", "status": "inProgress"},
            ]}

        with patch.object(main, "get_release", side_effect=fake_get_release):
            api = main.AzureApi("PAT")
            info = await api.get_task_info(1, 5, "stage-1")

        self.assertEqual(info["status"], "inProgress")
        self.assertIsNone(info["dependency_task_id"])
        self.assertIsNone(info["dependency_task_name"])

    async def test_get_task_info_unknown_environment_is_unknown(self):
        with patch.object(main, "get_release", side_effect=lambda p, r: {"environments": []}):
            api = main.AzureApi("PAT")
            info = await api.get_task_info(1, 999, "missing")
        self.assertEqual(info["status"], "Unknown")

    async def test_trigger_task_calls_trigger_release_task(self):
        calls = []

        def fake_trigger(pat, release_id, env_id):
            calls.append((pat, release_id, env_id))
            return {}

        with patch.object(main, "trigger_release_task", side_effect=fake_trigger):
            api = main.AzureApi("PAT")
            await api.trigger_task(1, 5)

        self.assertEqual(calls, [("PAT", 1, 5)])
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest test_main.py::AzureApiTests -q`
Expected: FAIL (`AttributeError: AzureApi`).

- [ ] **Step 3: Implement**

Append to `main.py` (under an `# ========= API seam =========` comment):

```python
# ========= API seam =========

class AzureApi:
    """Monitor API seam backed by Azure REST (stubbed HTTP). Blocking REST calls
    are offloaded to threads so they fit the async runner.

    Dependency cascade is not derived from Azure environment conditions in this
    iteration; deps are reported as None (each environment is triggered explicitly)."""

    def __init__(self, pat):
        self.pat = pat

    async def trigger_task(self, release_id, task_id) -> None:
        await asyncio.to_thread(trigger_release_task, self.pat, release_id, task_id)

    async def get_task_info(self, release_id, task_id, task_name) -> dict:
        data = await asyncio.to_thread(get_release, self.pat, release_id)
        env = next((e for e in data.get("environments", []) if e["id"] == task_id), None)
        return {
            "status": env["status"] if env else "Unknown",
            "dependency_task_id": None,
            "dependency_task_name": None,
        }
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest test_main.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add main.py test_main.py
git commit -m "feat: AzureApi seam adapter (stubbed HTTP)"
```

---

## Task 9: main() interactive flow + entry point

**Files:**
- Modify: `main.py`
- Test: `test_main.py`

- [ ] **Step 1: Write the failing smoke test**

Add to `test_main.py`:

```python
class MainFlowTests(unittest.TestCase):
    def test_main_happy_path_builds_runners_and_runs(self):
        inputs = iter(["app", "1", "1"])  # search text, definition pick, task pick
        captured = {}

        def fake_find(pat, text):
            return [("Deploy-App", 10)]

        def fake_create(pat, def_id):
            return 500

        def fake_get(pat, release_id):
            return {"name": "Deploy-App",
                    "environments": [{"id": 7, "name": "stage-1", "status": "notStarted"}]}

        async def fake_orch(runners, tasks, api, writer):
            captured["runners"] = runners
            captured["api"] = api

        argv = ["prog", "--pat", "SECRET"]
        with patch.object(sys, "argv", argv), \
             patch("builtins.input", side_effect=lambda *a: next(inputs)), \
             patch.object(main, "find_release_definition", side_effect=fake_find), \
             patch.object(main, "create_release", side_effect=fake_create), \
             patch.object(main, "get_release", side_effect=fake_get), \
             patch.object(main, "run_orchestration", side_effect=fake_orch):
            main.main()

        runners = captured["runners"]
        self.assertEqual(len(runners), 1)
        self.assertEqual(runners[0].release.name, "Deploy-App")
        self.assertEqual(runners[0].trigger_queue, ["stage-1"])
        self.assertIsInstance(captured["api"], main.AzureApi)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest test_main.py::MainFlowTests -q`
Expected: FAIL (`AttributeError: main` has no attribute `main`, or `_prompt_selection`).

- [ ] **Step 3: Implement `_prompt_selection` and `main()`**

Append to `main.py`:

```python
def _prompt_selection(prompt, count) -> list:
    """Prompt until a valid selection is entered; returns 0-based indices."""
    while True:
        try:
            return parse_selection(input(prompt), count)
        except ValueError as exc:
            print(f"Invalid selection: {exc}")


# ========= Main flow =========

def main():
    parser = argparse.ArgumentParser(description="Azure release task orchestrator")
    parser.add_argument("--pat", required=True, help="Azure DevOps Personal Access Token")
    pat = parser.parse_args().pat

    # Step 0-1: find release definitions (fuzzy) and pick.
    search = input("Release definition to search: ").strip()
    definitions = find_release_definition(pat, search)
    if not definitions:
        print("No matching release definitions.")
        return
    for i, (name, def_id) in enumerate(definitions, 1):
        print(f"  {i}. {name} (id={def_id})")
    selected = [definitions[i] for i in
                _prompt_selection("Select definitions to create (e.g. 1,3): ", len(definitions))]

    # Step 2-3: create each release, list environments, pick tasks.
    releases = []
    queue = []
    for name, def_id in selected:
        release_id = create_release(pat, def_id)
        data = get_release(pat, release_id)
        environments = data.get("environments", [])
        release = Release(
            id=release_id,
            name=data.get("name", name),
            available_tasks=[ReleaseTaskDef(id=e["id"], name=e["name"]) for e in environments],
        )
        print(f"\n{release.name} environments:")
        for i, env in enumerate(environments, 1):
            print(f"  {i}. {env['name']}")
        task_names = [environments[i]["name"] for i in
                      _prompt_selection("Select tasks to execute (e.g. 1,2): ", len(environments))]
        releases.append(release)
        queue.append((release.name, task_names))

    # Step 4: execute & monitor via monitor.py.
    runners = [ReleaseRunner.from_input(rn, tns, releases) for rn, tns in queue]
    tasks = {}
    writer = LiveWriter()
    api = AzureApi(pat)
    print("===Start===")
    try:
        asyncio.run(run_orchestration(runners, tasks, api, writer))
    except KeyboardInterrupt:
        print("\n===Cancelled===")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS (all `test_monitor.py` and `test_main.py` tests green).

- [ ] **Step 5: Commit**

```bash
git add main.py test_main.py
git commit -m "feat: interactive main() flow wiring find->create->select->orchestrate"
```

---

## Self-Review Notes

- **Spec coverage:** API seam (Task 1) ✓; MockApi (Task 1) ✓; AzureApi (Task 8) ✓; real REST shapes + single HTTP stub (Tasks 2-6) ✓; task=environment mapping (Task 8) ✓; `--pat`-only argparse + constants (Tasks 2, 9) ✓; interactive find→create→select flow (Task 9) ✓; selection parsing/re-prompt (Tasks 7, 9) ✓; error handling reuse (Task 1, unchanged) ✓; tests updated to FakeApi + new test_main.py (all tasks) ✓.
- **Type consistency:** seam methods `trigger_task(release_id, task_id)` / `get_task_info(release_id, task_id, task_name)` identical across `MockApi`, `AzureApi`, `FakeApi`; `get_task_info` always returns the `{status, dependency_task_id, dependency_task_name}` dict that `fetch_task_update` consumes; `run_orchestration(runners, tasks, api, writer)` called identically in `monitor()` and `main()`.
- **Known simplification (in scope):** `AzureApi.get_task_info` reports `dependency_*` as `None` — the cascade display remains a mock-only feature this iteration (noted in spec Out of Scope / Task 8 docstring).
