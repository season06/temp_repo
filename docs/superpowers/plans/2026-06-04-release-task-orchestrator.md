# Release Task Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `monitor.py` to actively trigger Azure release tasks (not just observe), serialized per release but parallel across releases, using asyncio.

**Architecture:** One `ReleaseRunner` coroutine per release walks a user-supplied trigger queue, calling `trigger_task` then polling its cascade chain until terminal before advancing. A separate `render_loop` coroutine repaints the terminal every 2s. Shared `tasks: dict[int, Task]` is safe because asyncio is single-threaded.

**Tech Stack:** Python 3.10+ stdlib only (asyncio, dataclasses, json, unittest). No external deps.

**Spec:** `docs/superpowers/specs/2026-06-04-release-task-orchestrator-design.md`

---

## File Map

| Path | Action | Responsibility |
|---|---|---|
| `mock_api.json` | Modify | New schema: `releases[].available_tasks[]`. |
| `monitor.py` | Modify (heavy) | Add ReleaseTaskDef/ReleaseRunner/TaskUpdate; async API; chain_terminal; asyncio main. |
| `test_monitor.py` | Modify (heavy) | Replace `poll_active_tasks` tests with runner tests; update render test. |

No new files. Single-module structure preserved per spec.

---

## Task 1: Restructure mock_api.json

**Files:**
- Modify: `mock_api.json`

- [ ] **Step 1: Replace contents**

```json
{
  "releases": [
    {
      "release_id": 1,
      "release_name": "release-1",
      "available_tasks": [
        { "task_id": 101, "task_name": "task-a" },
        { "task_id": 102, "task_name": "task-b" },
        { "task_id": 201, "task_name": "task-c" }
      ]
    }
  ],
  "tasks": {
    "101": { "status": "NotStarted", "dependency_task_id": 102, "dependency_task_name": "task-b" },
    "102": { "status": "NotStarted", "dependency_task_id": null, "dependency_task_name": null },
    "201": { "status": "NotStarted", "dependency_task_id": null, "dependency_task_name": null }
  }
}
```

- [ ] **Step 2: Verify JSON loads**

Run: `python3 -c "import json; print(json.load(open('mock_api.json'))['releases'][0]['release_name'])"`
Expected: `release-1`

- [ ] **Step 3: Commit**

```bash
git add mock_api.json
git commit -m "feat(mock): restructure mock_api.json to support per-release task lists"
```

---

## Task 2: Add new data models (ReleaseTaskDef, TaskUpdate already exists, new Release shape)

**Files:**
- Modify: `monitor.py`

Note: `Task` and `TaskUpdate` already exist. We are replacing the old `Release` dataclass.

- [ ] **Step 1: Write the failing tests**

Append to `test_monitor.py`:

```python
class DataModelTests(unittest.TestCase):
    def test_release_holds_available_tasks(self):
        release = monitor.Release(
            id=1,
            name="release-1",
            available_tasks=[
                monitor.ReleaseTaskDef(id=101, name="task-a"),
                monitor.ReleaseTaskDef(id=102, name="task-b"),
            ],
        )
        self.assertEqual(release.available_tasks[0].name, "task-a")
        self.assertEqual(release.available_tasks[1].id, 102)

    def test_release_task_def_is_frozen(self):
        td = monitor.ReleaseTaskDef(id=101, name="task-a")
        with self.assertRaises(Exception):
            td.id = 999
```

- [ ] **Step 2: Run tests — expected FAIL**

Run: `python3 -m unittest test_monitor.DataModelTests -v`
Expected: FAIL with `AttributeError: module 'monitor' has no attribute 'ReleaseTaskDef'` (or similar)

- [ ] **Step 3: Replace the Release dataclass in monitor.py**

Find existing block in `monitor.py`:

```python
@dataclass(frozen=True)
class Release:
    """A release entry pointing at its root task."""
    id: int
    name: str
    root_task_id: int
    root_task_name: str
```

Replace with:

```python
@dataclass(frozen=True)
class ReleaseTaskDef:
    """One task slot inside a release pipeline. Provides name↔id mapping."""
    id: int
    name: str


@dataclass(frozen=True)
class Release:
    """Release metadata. `available_tasks` lists every task triggerable from this pipeline."""
    id: int
    name: str
    available_tasks: list[ReleaseTaskDef]
```

- [ ] **Step 4: Run tests — expected PASS**

Run: `python3 -m unittest test_monitor.DataModelTests -v`
Expected: PASS

- [ ] **Step 5: Note: existing tests will fail now**

Run: `python3 -m unittest test_monitor -v`
Expected: existing `test_poll_active_tasks_discovers_nested_dependencies` and `test_render_monitoring_displays_nested_dependencies` now FAIL because they use old `Release(root_task_id=..., root_task_name=...)` signature. **Do not fix them in this task** — they get replaced wholesale in Tasks 6 and 9. Mark them as expected failures temporarily:

Edit `test_monitor.py` — add `@unittest.skip("replaced in Task 6/9")` decorator above:
- `test_poll_active_tasks_discovers_nested_dependencies`
- `test_render_monitoring_displays_nested_dependencies`

- [ ] **Step 6: Verify all currently active tests pass**

Run: `python3 -m unittest test_monitor -v`
Expected: 2 skipped, others pass

- [ ] **Step 7: Commit**

```bash
git add monitor.py test_monitor.py
git commit -m "feat: introduce ReleaseTaskDef, restructure Release for multi-task pipelines"
```

---

## Task 3: Add ReleaseRunner dataclass + from_input + _resolve_name

**Files:**
- Modify: `monitor.py`
- Modify: `test_monitor.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_monitor.py`:

```python
class ReleaseRunnerConstructionTests(unittest.TestCase):
    def _release(self):
        return monitor.Release(
            id=1,
            name="release-1",
            available_tasks=[
                monitor.ReleaseTaskDef(id=101, name="task-a"),
                monitor.ReleaseTaskDef(id=201, name="task-c"),
            ],
        )

    def test_from_input_resolves_release_and_tasks(self):
        runner = monitor.ReleaseRunner.from_input(
            "release-1", ["task-a", "task-c"], [self._release()]
        )
        self.assertEqual(runner.release.name, "release-1")
        self.assertEqual(runner.trigger_queue, ["task-a", "task-c"])
        self.assertEqual(runner.triggered, [])
        self.assertIsNone(runner.active_root_id)
        self.assertFalse(runner.is_done())

    def test_from_input_raises_on_unknown_release(self):
        with self.assertRaises(ValueError):
            monitor.ReleaseRunner.from_input("nope", ["task-a"], [self._release()])

    def test_from_input_raises_on_unknown_task_name(self):
        with self.assertRaises(ValueError):
            monitor.ReleaseRunner.from_input("release-1", ["task-x"], [self._release()])

    def test_resolve_name_returns_task_id(self):
        runner = monitor.ReleaseRunner.from_input("release-1", ["task-a"], [self._release()])
        self.assertEqual(runner._resolve_name("task-a"), 101)
        self.assertEqual(runner._resolve_name("task-c"), 201)
```

- [ ] **Step 2: Run tests — expected FAIL**

Run: `python3 -m unittest test_monitor.ReleaseRunnerConstructionTests -v`
Expected: FAIL with `AttributeError: module 'monitor' has no attribute 'ReleaseRunner'`

- [ ] **Step 3: Add ReleaseRunner to monitor.py**

Add after the existing `TaskUpdate` dataclass (or after Release):

```python
@dataclass
class ReleaseRunner:
    """Per-release coordinator. Walks `trigger_queue` sequentially, triggering and
    waiting for each task's cascade chain to reach terminal status."""
    release: Release
    trigger_queue: list[str]
    triggered: list[int]
    active_root_id: int | None = None
    _done: bool = False

    @classmethod
    def from_input(cls, release_name: str, task_names: list[str],
                   releases: list[Release]) -> "ReleaseRunner":
        release = next((r for r in releases if r.name == release_name), None)
        if release is None:
            raise ValueError(f"unknown release: {release_name}")
        available_names = {t.name for t in release.available_tasks}
        for name in task_names:
            if name not in available_names:
                raise ValueError(f"task {name!r} not in release {release_name!r}")
        return cls(release=release, trigger_queue=list(task_names), triggered=[])

    def is_done(self) -> bool:
        return self._done

    def _resolve_name(self, name: str) -> int:
        for td in self.release.available_tasks:
            if td.name == name:
                return td.id
        raise ValueError(f"task {name!r} not in release {self.release.name!r}")
```

- [ ] **Step 4: Run tests — expected PASS**

Run: `python3 -m unittest test_monitor.ReleaseRunnerConstructionTests -v`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add monitor.py test_monitor.py
git commit -m "feat: add ReleaseRunner with name→id resolution"
```

---

## Task 4: Add chain_terminal pure function

**Files:**
- Modify: `monitor.py`
- Modify: `test_monitor.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_monitor.py`:

```python
class ChainTerminalTests(unittest.TestCase):
    def test_all_terminal_returns_true(self):
        tasks = {
            101: monitor.Task(id=101, name="task-a", status="Successed", dependency_id=102, dependency_name="task-b"),
            102: monitor.Task(id=102, name="task-b", status="Failed"),
        }
        self.assertTrue(monitor.chain_terminal(101, tasks))

    def test_partial_terminal_returns_false(self):
        tasks = {
            101: monitor.Task(id=101, name="task-a", status="Successed", dependency_id=102, dependency_name="task-b"),
            102: monitor.Task(id=102, name="task-b", status="InProgress"),
        }
        self.assertFalse(monitor.chain_terminal(101, tasks))

    def test_root_not_terminal_returns_false(self):
        tasks = {101: monitor.Task(id=101, name="task-a", status="InProgress")}
        self.assertFalse(monitor.chain_terminal(101, tasks))

    def test_handles_cycle(self):
        tasks = {
            101: monitor.Task(id=101, name="task-a", status="Successed", dependency_id=102, dependency_name="task-b"),
            102: monitor.Task(id=102, name="task-b", status="Successed", dependency_id=101, dependency_name="task-a"),
        }
        self.assertTrue(monitor.chain_terminal(101, tasks))

    def test_handles_broken_chain_when_dep_missing(self):
        # dep_id points at 999 but tasks[999] doesn't exist
        tasks = {
            101: monitor.Task(id=101, name="task-a", status="Successed", dependency_id=999, dependency_name="ghost"),
        }
        self.assertFalse(monitor.chain_terminal(101, tasks))

    def test_error_status_is_not_terminal(self):
        tasks = {101: monitor.Task(id=101, name="task-a", status="Error")}
        self.assertFalse(monitor.chain_terminal(101, tasks))
```

- [ ] **Step 2: Run tests — expected FAIL**

Run: `python3 -m unittest test_monitor.ChainTerminalTests -v`
Expected: FAIL with `AttributeError: module 'monitor' has no attribute 'chain_terminal'`

- [ ] **Step 3: Add chain_terminal to monitor.py**

Add after `is_terminate_status`:

```python
def chain_terminal(root_id: int, tasks: dict) -> bool:
    """Return True when root + its entire dependency chain are all in a terminal status."""
    seen = set()
    current_id = root_id
    while current_id is not None and current_id not in seen:
        seen.add(current_id)
        task = tasks.get(current_id)
        if task is None or not is_terminate_status(task.status):
            return False
        current_id = task.dependency_id
    return True
```

- [ ] **Step 4: Run tests — expected PASS**

Run: `python3 -m unittest test_monitor.ChainTerminalTests -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add monitor.py test_monitor.py
git commit -m "feat: add chain_terminal helper"
```

---

## Task 5: Convert API layer to async + add trigger_task + get_release_metadata

**Files:**
- Modify: `monitor.py`
- Modify: `test_monitor.py`

This refactors existing sync IO to async and adds the two new functions.

- [ ] **Step 1: Write the failing tests**

Append to `test_monitor.py`. Note `IsolatedAsyncioTestCase`:

```python
import asyncio
import json
import os
import tempfile
from unittest import IsolatedAsyncioTestCase


class AsyncApiTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._original_mock_file = monitor.MOCK_API_FILE
        monitor.MOCK_API_FILE = os.path.join(self._tmpdir, "mock.json")
        with open(monitor.MOCK_API_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "releases": [{
                    "release_id": 1,
                    "release_name": "release-1",
                    "available_tasks": [
                        {"task_id": 101, "task_name": "task-a"},
                        {"task_id": 102, "task_name": "task-b"},
                    ],
                }],
                "tasks": {
                    "101": {"status": "NotStarted", "dependency_task_id": 102, "dependency_task_name": "task-b"},
                    "102": {"status": "NotStarted", "dependency_task_id": None, "dependency_task_name": None},
                },
            }, f)

    async def asyncTearDown(self):
        monitor.MOCK_API_FILE = self._original_mock_file
        import shutil
        shutil.rmtree(self._tmpdir)

    async def test_get_release_metadata_returns_releases(self):
        releases = await monitor.get_release_metadata()
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0].name, "release-1")
        self.assertEqual(releases[0].available_tasks[0].name, "task-a")
        self.assertEqual(releases[0].available_tasks[0].id, 101)

    async def test_get_release_task_info_returns_dict(self):
        info = await monitor.get_release_task_info(101)
        self.assertEqual(info["status"], "NotStarted")
        self.assertEqual(info["dependency_task_id"], 102)

    async def test_get_release_task_info_raises_on_unknown(self):
        with self.assertRaises(KeyError):
            await monitor.get_release_task_info(999)

    async def test_trigger_task_sets_status_to_inprogress(self):
        await monitor.trigger_task(101)
        info = await monitor.get_release_task_info(101)
        self.assertEqual(info["status"], "InProgress")

    async def test_trigger_task_is_idempotent(self):
        await monitor.trigger_task(101)
        await monitor.trigger_task(101)  # second call should not raise
        info = await monitor.get_release_task_info(101)
        self.assertEqual(info["status"], "InProgress")

    async def test_fetch_task_update_returns_error_on_failure(self):
        update = await monitor.fetch_task_update(999)
        self.assertEqual(update.status, "Error")
        self.assertIsNone(update.dependency_id)
```

- [ ] **Step 2: Run tests — expected FAIL**

Run: `python3 -m unittest test_monitor.AsyncApiTests -v`
Expected: FAIL (functions are sync, return values don't match async expectations, or `trigger_task` / `get_release_metadata` don't exist)

- [ ] **Step 3: Update monitor.py API layer**

Add `import asyncio` at top.

Replace `read_mock_api_file` block:

```python
async def read_mock_api_file() -> dict:
    """Read the mock API JSON file used to simulate live status updates."""
    def _read():
        with open(MOCK_API_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    return await asyncio.to_thread(_read)


async def _write_mock_api_file(data: dict) -> None:
    """Write back the mock API JSON file. Mock-only — prod has no analog."""
    def _write():
        with open(MOCK_API_FILE, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)
    await asyncio.to_thread(_write)
```

Remove the old `get_release_info()` function entirely.

Add:

```python
async def get_release_metadata() -> list:
    """Return all releases with their available task definitions."""
    data = await read_mock_api_file()
    return [
        Release(
            id=r["release_id"],
            name=r["release_name"],
            available_tasks=[
                ReleaseTaskDef(id=t["task_id"], name=t["task_name"])
                for t in r["available_tasks"]
            ],
        )
        for r in data["releases"]
    ]
```

Replace `get_release_task_info`:

```python
async def get_release_task_info(task_id) -> dict:
    """Return the latest task status from the mock file."""
    data = await read_mock_api_file()
    task_data = data["tasks"].get(str(task_id))
    if task_data is None:
        raise KeyError(f"task not found: {task_id}")
    return {
        "status": task_data.get("status", "Unknown"),
        "dependency_task_id": task_data.get("dependency_task_id"),
        "dependency_task_name": task_data.get("dependency_task_name"),
    }
```

Add (after `get_release_task_info`):

```python
async def trigger_task(task_id) -> None:
    """MOCK ONLY: force the task's status to InProgress. Idempotent.
    In prod, this becomes an HTTP POST to the Azure release pipeline."""
    data = await read_mock_api_file()
    task_data = data["tasks"].get(str(task_id))
    if task_data is None:
        raise KeyError(f"task not found: {task_id}")
    task_data["status"] = "InProgress"
    await _write_mock_api_file(data)
```

Replace `fetch_task_update`:

```python
async def fetch_task_update(task_id) -> TaskUpdate:
    """Fetch latest task state via the API. Return an Error update if the call fails."""
    try:
        info = await get_release_task_info(task_id)
    except Exception:
        return TaskUpdate(status="Error")
    return TaskUpdate(
        status=info.get("status", "Unknown"),
        dependency_id=info.get("dependency_task_id"),
        dependency_name=info.get("dependency_task_name"),
    )
```

- [ ] **Step 4: Run async tests — expected PASS**

Run: `python3 -m unittest test_monitor.AsyncApiTests -v`
Expected: 6 PASS

- [ ] **Step 5: Confirm other tests still work**

Run: `python3 -m unittest test_monitor -v`
Expected: 2 skipped (from Task 2), DataModel + ReleaseRunnerConstruction + ChainTerminal + AsyncApi all PASS

- [ ] **Step 6: Commit**

```bash
git add monitor.py test_monitor.py
git commit -m "feat: async API layer + trigger_task + get_release_metadata"
```

---

## Task 6: Convert poll_task to async; remove poll_active_tasks

**Files:**
- Modify: `monitor.py`
- Modify: `test_monitor.py`

- [ ] **Step 1: Write the failing test**

Append to `test_monitor.py`:

```python
class PollTaskAsyncTests(IsolatedAsyncioTestCase):
    async def test_poll_task_updates_in_place(self):
        task = monitor.Task(id=101, name="task-a")

        async def fake_fetch(task_id):
            return monitor.TaskUpdate(status="InProgress", dependency_id=102, dependency_name="task-b")

        with patch.object(monitor, "fetch_task_update", side_effect=fake_fetch):
            new_dep = await monitor.poll_task(task)

        self.assertEqual(task.status, "InProgress")
        self.assertEqual(task.dependency_id, 102)
        self.assertIsNotNone(new_dep)
        self.assertEqual(new_dep.id, 102)
        self.assertEqual(new_dep.name, "task-b")

    async def test_poll_task_skips_when_terminal(self):
        task = monitor.Task(id=101, name="task-a", status="Successed")

        async def fake_fetch(task_id):
            raise AssertionError("should not be called")

        with patch.object(monitor, "fetch_task_update", side_effect=fake_fetch):
            result = await monitor.poll_task(task)

        self.assertIsNone(result)

    async def test_poll_task_returns_none_when_no_dep(self):
        task = monitor.Task(id=102, name="task-b")

        async def fake_fetch(task_id):
            return monitor.TaskUpdate(status="InProgress")

        with patch.object(monitor, "fetch_task_update", side_effect=fake_fetch):
            result = await monitor.poll_task(task)

        self.assertIsNone(result)
```

Then delete the old `test_poll_active_tasks_discovers_nested_dependencies` method entirely (was skipped in Task 2).

- [ ] **Step 2: Run tests — expected FAIL**

Run: `python3 -m unittest test_monitor.PollTaskAsyncTests -v`
Expected: FAIL — `poll_task` is sync, mocked `fetch_task_update` returns coroutine but old code doesn't await.

- [ ] **Step 3: Update monitor.py**

Replace `poll_task`:

```python
async def poll_task(task):
    """Apply the latest update to a task. Return the newly discovered dependency, if any."""
    if is_terminate_status(task.status):
        return None

    update = await fetch_task_update(task.id)
    task.status = update.status
    task.dependency_id = update.dependency_id
    task.dependency_name = update.dependency_name

    if update.dependency_id and update.dependency_name:
        return Task(id=update.dependency_id, name=update.dependency_name)

    return None
```

Delete the entire `poll_active_tasks` function (was `# PROD PORTABLE.` block).

Delete the entire `all_tasks_terminated` function — it will not be used by the new asyncio main.

- [ ] **Step 4: Run tests — expected PASS**

Run: `python3 -m unittest test_monitor.PollTaskAsyncTests -v`
Expected: 3 PASS

- [ ] **Step 5: Run full suite — confirm nothing else broke**

Run: `python3 -m unittest test_monitor -v`
Expected: render test still skipped (gets replaced in Task 9); everything else PASS

- [ ] **Step 6: Commit**

```bash
git add monitor.py test_monitor.py
git commit -m "refactor: async poll_task; remove obsolete poll_active_tasks and all_tasks_terminated"
```

---

## Task 7: Implement ReleaseRunner._poll_chain + _wait_chain_terminal

**Files:**
- Modify: `monitor.py`
- Modify: `test_monitor.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_monitor.py`:

```python
class PollChainTests(IsolatedAsyncioTestCase):
    def _runner(self):
        release = monitor.Release(
            id=1, name="release-1",
            available_tasks=[
                monitor.ReleaseTaskDef(id=101, name="task-a"),
                monitor.ReleaseTaskDef(id=102, name="task-b"),
                monitor.ReleaseTaskDef(id=201, name="task-c"),
            ],
        )
        return monitor.ReleaseRunner.from_input("release-1", ["task-a", "task-c"], [release])

    async def test_poll_chain_discovers_dependency(self):
        runner = self._runner()
        tasks = {101: monitor.Task(id=101, name="task-a")}

        responses = {
            101: monitor.TaskUpdate(status="InProgress", dependency_id=102, dependency_name="task-b"),
            102: monitor.TaskUpdate(status="NotStarted"),
        }

        async def fake_fetch(task_id):
            return responses[task_id]

        with patch.object(monitor, "fetch_task_update", side_effect=fake_fetch):
            await runner._poll_chain(101, tasks)

        self.assertIn(102, tasks)
        self.assertEqual(tasks[102].name, "task-b")
        self.assertEqual(tasks[101].status, "InProgress")
        self.assertEqual(tasks[102].status, "NotStarted")
```

- [ ] **Step 2: Run test — expected FAIL**

Run: `python3 -m unittest test_monitor.PollChainTests -v`
Expected: FAIL — `_poll_chain` method does not exist

- [ ] **Step 3: Add methods to ReleaseRunner**

Add inside the `ReleaseRunner` class (after `_resolve_name`):

```python
    async def _poll_chain(self, root_id: int, tasks: dict) -> None:
        """Poll root + all known cascade tasks once. Newly discovered deps join `tasks`."""
        worklist = [tasks[root_id]]
        seen = set()
        while worklist:
            task = worklist.pop()
            if task.id in seen:
                continue
            seen.add(task.id)

            new_dep = await poll_task(task)
            if new_dep and new_dep.id not in tasks:
                tasks[new_dep.id] = new_dep
                worklist.append(new_dep)
            elif task.dependency_id and task.dependency_id in tasks:
                worklist.append(tasks[task.dependency_id])

    async def _wait_chain_terminal(self, root_id: int, tasks: dict) -> None:
        """Poll-and-wait until root's chain is fully terminal."""
        while True:
            await self._poll_chain(root_id, tasks)
            if chain_terminal(root_id, tasks):
                return
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
```

Also add this constant near the top of `monitor.py` (after `MOCK_API_FILE`):

```python
POLL_INTERVAL_SECONDS = 2
```

- [ ] **Step 4: Run test — expected PASS**

Run: `python3 -m unittest test_monitor.PollChainTests -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add monitor.py test_monitor.py
git commit -m "feat: ReleaseRunner._poll_chain + _wait_chain_terminal"
```

---

## Task 8: Implement ReleaseRunner.run

**Files:**
- Modify: `monitor.py`
- Modify: `test_monitor.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_monitor.py`:

```python
class ReleaseRunnerRunTests(IsolatedAsyncioTestCase):
    def _release(self):
        return monitor.Release(
            id=1, name="release-1",
            available_tasks=[
                monitor.ReleaseTaskDef(id=101, name="task-a"),
                monitor.ReleaseTaskDef(id=102, name="task-b"),
                monitor.ReleaseTaskDef(id=201, name="task-c"),
            ],
        )

    async def test_run_triggers_queue_sequentially(self):
        """trigger order must be [101, 201]; 201 not triggered until 101+cascade terminal."""
        runner = monitor.ReleaseRunner.from_input(
            "release-1", ["task-a", "task-c"], [self._release()],
        )
        tasks = {}

        trigger_order = []

        async def fake_trigger(tid):
            trigger_order.append(tid)

        # Simulate API: 101 has dep 102; both go straight to Successed; 201 standalone, Successed
        status_table = {
            101: monitor.TaskUpdate(status="Successed", dependency_id=102, dependency_name="task-b"),
            102: monitor.TaskUpdate(status="Successed"),
            201: monitor.TaskUpdate(status="Successed"),
        }

        async def fake_fetch(task_id):
            return status_table[task_id]

        with patch.object(monitor, "trigger_task", side_effect=fake_trigger), \
             patch.object(monitor, "fetch_task_update", side_effect=fake_fetch):
            await runner.run(tasks)

        self.assertEqual(trigger_order, [101, 201])
        self.assertTrue(runner.is_done())
        self.assertEqual(runner.triggered, [101, 201])
        self.assertIsNone(runner.active_root_id)

    async def test_run_waits_for_cascade_before_advancing(self):
        """task-c is not triggered until task-a AND task-b reach terminal."""
        runner = monitor.ReleaseRunner.from_input(
            "release-1", ["task-a", "task-c"], [self._release()],
        )
        tasks = {}

        trigger_order = []
        poll_count = {101: 0, 102: 0, 201: 0}

        async def fake_trigger(tid):
            trigger_order.append(tid)

        async def fake_fetch(task_id):
            poll_count[task_id] += 1
            # task-a always Successed; task-b reports InProgress twice, then Successed
            # task-c reports Successed when polled
            if task_id == 101:
                return monitor.TaskUpdate(status="Successed", dependency_id=102, dependency_name="task-b")
            if task_id == 102:
                if poll_count[102] < 3:
                    return monitor.TaskUpdate(status="InProgress")
                return monitor.TaskUpdate(status="Successed")
            if task_id == 201:
                return monitor.TaskUpdate(status="Successed")

        async def no_sleep(_):
            return

        with patch.object(monitor, "trigger_task", side_effect=fake_trigger), \
             patch.object(monitor, "fetch_task_update", side_effect=fake_fetch), \
             patch.object(monitor.asyncio, "sleep", side_effect=no_sleep):
            await runner.run(tasks)

        # task-c only triggered after task-b polled to Successed
        self.assertEqual(trigger_order, [101, 201])
        self.assertGreaterEqual(poll_count[102], 3)

    async def test_run_continues_after_trigger_failure(self):
        """trigger_task raises for 101 → task is marked Error, run() advances to 201."""
        runner = monitor.ReleaseRunner.from_input(
            "release-1", ["task-a", "task-c"], [self._release()],
        )
        tasks = {}
        trigger_order = []

        async def fake_trigger(tid):
            trigger_order.append(tid)
            if tid == 101:
                raise ConnectionError("simulated")

        async def fake_fetch(task_id):
            return monitor.TaskUpdate(status="Successed")

        with patch.object(monitor, "trigger_task", side_effect=fake_trigger), \
             patch.object(monitor, "fetch_task_update", side_effect=fake_fetch):
            await runner.run(tasks)

        self.assertEqual(trigger_order, [101, 201])
        self.assertEqual(tasks[101].status, "Error")
        self.assertTrue(runner.is_done())

    async def test_run_continues_after_task_failure(self):
        """task-a returns Failed (a terminal status) → 201 still triggered."""
        runner = monitor.ReleaseRunner.from_input(
            "release-1", ["task-a", "task-c"], [self._release()],
        )
        tasks = {}
        trigger_order = []

        async def fake_trigger(tid):
            trigger_order.append(tid)

        async def fake_fetch(task_id):
            if task_id == 101:
                return monitor.TaskUpdate(status="Failed")
            return monitor.TaskUpdate(status="Successed")

        with patch.object(monitor, "trigger_task", side_effect=fake_trigger), \
             patch.object(monitor, "fetch_task_update", side_effect=fake_fetch):
            await runner.run(tasks)

        self.assertEqual(trigger_order, [101, 201])
        self.assertEqual(tasks[101].status, "Failed")
```

- [ ] **Step 2: Run tests — expected FAIL**

Run: `python3 -m unittest test_monitor.ReleaseRunnerRunTests -v`
Expected: FAIL — `run` method doesn't exist

- [ ] **Step 3: Add run() method to ReleaseRunner**

Add inside the `ReleaseRunner` class (after `_wait_chain_terminal`):

```python
    async def run(self, tasks: dict) -> None:
        """Walk the trigger queue. Trigger each task and wait for its chain to terminate
        before moving on. Trigger failures mark the task Error and advance."""
        for name in self.trigger_queue:
            tid = self._resolve_name(name)
            self.active_root_id = tid
            self.triggered.append(tid)
            tasks[tid] = Task(id=tid, name=name)

            try:
                await trigger_task(tid)
            except Exception:
                tasks[tid].status = "Error"
                self.active_root_id = None
                continue

            await self._wait_chain_terminal(tid, tasks)
            self.active_root_id = None

        self._done = True
```

- [ ] **Step 4: Run tests — expected PASS**

Run: `python3 -m unittest test_monitor.ReleaseRunnerRunTests -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add monitor.py test_monitor.py
git commit -m "feat: ReleaseRunner.run orchestrates trigger queue sequentially"
```

---

## Task 9: Update render_monitoring for runners-based input

**Files:**
- Modify: `monitor.py`
- Modify: `test_monitor.py`

- [ ] **Step 1: Replace the skipped render test**

In `test_monitor.py`, delete the entire `test_render_monitoring_displays_nested_dependencies` method (was skipped). Add new tests:

```python
class RenderMonitoringTests(unittest.TestCase):
    def _release(self):
        return monitor.Release(
            id=1, name="release-1",
            available_tasks=[
                monitor.ReleaseTaskDef(id=101, name="task-a"),
                monitor.ReleaseTaskDef(id=102, name="task-b"),
                monitor.ReleaseTaskDef(id=201, name="task-c"),
            ],
        )

    def test_renders_pending_then_active_then_done(self):
        runner = monitor.ReleaseRunner.from_input(
            "release-1", ["task-a", "task-c"], [self._release()],
        )
        # Simulate state: task-a triggered, cascading; task-c still pending
        runner.triggered = [101]
        runner.active_root_id = 101
        tasks = {
            101: monitor.Task(id=101, name="task-a", status="InProgress",
                              dependency_id=102, dependency_name="task-b"),
            102: monitor.Task(id=102, name="task-b", status="NotStarted"),
        }

        output = monitor.render_monitoring([runner], tasks)

        self.assertIn("=== release-1 ===", output)
        self.assertIn("task-a : InProgress ◀ active", output)
        self.assertIn("|_task-b : NotStarted", output)
        self.assertIn("task-c : Pending", output)

    def test_renders_completed_task_without_active_marker(self):
        runner = monitor.ReleaseRunner.from_input(
            "release-1", ["task-a", "task-c"], [self._release()],
        )
        runner.triggered = [101, 201]
        runner.active_root_id = 201
        tasks = {
            101: monitor.Task(id=101, name="task-a", status="Successed",
                              dependency_id=102, dependency_name="task-b"),
            102: monitor.Task(id=102, name="task-b", status="Successed"),
            201: monitor.Task(id=201, name="task-c", status="InProgress"),
        }

        output = monitor.render_monitoring([runner], tasks)
        lines = output.splitlines()

        # task-a line must NOT have ◀ active marker; task-c MUST
        task_a_line = next(line for line in lines if line.strip().startswith("task-a"))
        task_c_line = next(line for line in lines if line.strip().startswith("task-c"))
        self.assertNotIn("◀ active", task_a_line)
        self.assertIn("◀ active", task_c_line)
```

- [ ] **Step 2: Run test — expected FAIL**

Run: `python3 -m unittest test_monitor.RenderMonitoringTests -v`
Expected: FAIL — old `render_monitoring(releases, tasks)` signature does not match

- [ ] **Step 3: Replace render_monitoring in monitor.py**

Find the existing `render_monitoring` function and replace entirely with:

```python
def render_monitoring(runners: list, tasks: dict) -> str:
    """Render every release's progress: triggered tasks (with cascade) + pending tail."""
    lines = []
    for runner in runners:
        lines.append(f"=== {runner.release.name} ===")

        for tid in runner.triggered:
            root = tasks.get(tid)
            marker = " ◀ active" if tid == runner.active_root_id else ""
            status = root.status if root else "Waiting"
            name = root.name if root else "?"
            lines.append(f"  {name} : {status}{marker}")

            indent = "    "
            current = root
            seen = {tid}
            while current and current.dependency_id and current.dependency_id not in seen:
                seen.add(current.dependency_id)
                dep = tasks.get(current.dependency_id)
                dep_status = dep.status if dep else "Waiting"
                lines.append(f"{indent}|_{current.dependency_name} : {dep_status}")
                indent += "  "
                current = dep

        for name in runner.trigger_queue[len(runner.triggered):]:
            lines.append(f"  {name} : Pending")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests — expected PASS**

Run: `python3 -m unittest test_monitor.RenderMonitoringTests -v`
Expected: 2 PASS

- [ ] **Step 5: Full suite check**

Run: `python3 -m unittest test_monitor -v`
Expected: all tests PASS, no skipped left (both originally skipped tests have now been deleted/replaced)

- [ ] **Step 6: Commit**

```bash
git add monitor.py test_monitor.py
git commit -m "feat: render_monitoring takes runners; shows triggered+pending per release"
```

---

## Task 10: Rewrite main() with asyncio + render_loop

**Files:**
- Modify: `monitor.py`

- [ ] **Step 1: Replace main() and add render_loop**

Find the existing `main()` function in `monitor.py` and replace the entire block from `# PROD PORTABLE with one prod change:` through the `if __name__ == "__main__": main()` with:

```python
# PROD PORTABLE: independent render heartbeat. Keeps rendering while any runner is alive.
async def render_loop(runners: list, tasks: dict, writer: LiveWriter) -> None:
    while not all(r.is_done() for r in runners):
        writer.write(render_monitoring(runners, tasks))
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    writer.write(render_monitoring(runners, tasks))  # final paint


# PROD PORTABLE with one prod change: replace be_trigger_release with real input source.
async def main() -> None:
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
    print("===Start===")

    try:
        await asyncio.gather(
            *(r.run(tasks) for r in runners),
            render_loop(runners, tasks, writer),
        )
    except KeyboardInterrupt:
        print("\n===Cancelled===")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Smoke-test the script end-to-end against the mock**

First reset mock_api.json to its initial NotStarted state (Task 1 contents). Then in one terminal:

```bash
python3 monitor.py
```

Expected: prints `===Start===`, then shows:
```
=== release-1 ===
  task-a : InProgress ◀ active
    |_task-b : NotStarted
  task-c : Pending
```

In another terminal, edit `mock_api.json` to advance state. After each edit, the running script should update within ~2s:

a. Set `"101": {"status": "Successed", ...}` → task-a shows Successed (still active marker — waiting for cascade)
b. Set `"102": {"status": "InProgress", ...}` → task-b shows InProgress
c. Set `"102": {"status": "Successed", ...}` → cascade terminal → script triggers task-c → task-c InProgress ◀ active
d. Set `"201": {"status": "Successed"}` → task-c Successed, script exits

- [ ] **Step 3: Verify clean exit**

Expected: when all triggered tasks are terminal, the script exits cleanly (no hang, no traceback).

- [ ] **Step 4: Run full test suite**

Run: `python3 -m unittest test_monitor -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add monitor.py
git commit -m "feat: asyncio main with render_loop and per-release runners"
```

---

## Task 11: Final cleanup pass

**Files:**
- Modify: `monitor.py`

- [ ] **Step 1: Remove dead code & stale comments**

Verify these are removed from `monitor.py`:
- `get_release_info()` function
- `poll_active_tasks()` function
- `all_tasks_terminated()` function
- `write_live_update()` if it exists as a free function (should now only live as `LiveWriter.write`)

Verify these comments are updated to reflect async:
- `# PROD PORTABLE` markers next to functions that are now async

- [ ] **Step 2: Sanity-grep for old symbols**

Run: `grep -nE "poll_active_tasks|all_tasks_terminated|get_release_info|root_task_id" monitor.py test_monitor.py`
Expected: no matches (or only matches inside docstrings/comments that explain the new design)

- [ ] **Step 3: Final test run**

Run: `python3 -m unittest test_monitor -v`
Expected: all tests PASS, zero skipped.

- [ ] **Step 4: Commit if anything changed**

```bash
git add monitor.py
git commit -m "chore: cleanup dead code and stale comments"
```

If nothing changed in this task, skip commit.

---

## Self-Review Notes

**Spec coverage check:**

| Spec section | Plan task |
|---|---|
| Functional: accept be_trigger_release input | Task 10 (main) |
| Functional: one task per release at a time | Task 8 (run loop is sequential per runner) |
| Functional: multi-release parallel | Task 10 (asyncio.gather over runners) |
| Functional: continue on failure | Task 8 tests |
| Functional: terminal status definitions | Task 4 (chain_terminal) |
| Functional: live terminal view | Task 9 (render) + Task 10 (render_loop) |
| Non-functional: stdlib only | Verified — only asyncio/json/dataclasses |
| Data model: Task, TaskUpdate, ReleaseTaskDef, Release, ReleaseRunner | Tasks 2, 3 (TaskUpdate already exists from prior work) |
| Mock API: schema + 5 functions | Tasks 1, 5 |
| Runner flow | Tasks 7, 8 |
| Render | Task 9 |
| Error handling: trigger failure, poll failure, Error not terminal, unknown name, etc | Tasks 3, 5, 6, 8 |
| Main entry | Task 10 |
| File layout: single monitor.py | Confirmed |
| Testing matrix | Tasks 2, 3, 4, 5, 6, 7, 8, 9 |

All spec items covered.

**Type consistency check:**
- `ReleaseRunner.from_input(release_name, task_names, releases)` — same signature in Task 3 and Task 10. ✓
- `chain_terminal(root_id, tasks)` — same in Task 4, Task 7. ✓
- `poll_task(task)` returns `Task | None` — consistent Task 6, 7. ✓
- `fetch_task_update(task_id) → TaskUpdate` — consistent Task 5, 6. ✓
- `trigger_task(task_id) → None` — consistent Task 5, 8. ✓
- `render_monitoring(runners, tasks)` — consistent Task 9, 10. ✓
- `POLL_INTERVAL_SECONDS` introduced Task 7, used Task 10. ✓

No placeholders. No "TBD" / "TODO" / "implement later".
