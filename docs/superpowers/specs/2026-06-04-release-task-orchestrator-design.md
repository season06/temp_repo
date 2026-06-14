# Release Task Orchestrator — Design Spec

**Date:** 2026-06-04
**Status:** Approved, awaiting implementation plan
**Author:** brainstormed with user

## Goal

Extend the existing Azure release monitor to also **orchestrate** task execution, not just observe. The user specifies which tasks of which releases to run, and the script triggers them sequentially within each release (one task at a time per release) while running multiple releases concurrently.

## Requirements

### Functional
- Accept input `be_trigger_release: list[tuple[str, list[str]]]` — for each release, the ordered list of task names to trigger.
- Within a single release, trigger one task at a time. Wait until the triggered task **and its cascaded dependency chain** all reach a terminal status before triggering the next task in the queue.
- Across releases, run concurrently (different releases progress in parallel).
- Continue to the next queued task even if the previous one failed/cancelled. Terminal status = `Successed | Failed | Canceled` (lowercased match).
- Render a live terminal view showing every triggered task (past and current) and its dependency cascade.

### Non-functional
- Single-file Python script (`monitor.py`), no external dependencies beyond stdlib.
- asyncio-based concurrency; no threads, no processes.
- Mock API via local JSON file; structure compatible with future Azure REST API swap-in.

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  asyncio event loop                                            │
│                                                                │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │ ReleaseRunner-1 │    │ ReleaseRunner-N │  one coroutine     │
│  │  queue:[a, c]   │    │  queue:[...]    │  per release       │
│  │  active: None   │    │  active: ...    │                    │
│  └────────┬────────┘    └────────┬────────┘                    │
│           │                      │                              │
│           ▼                      ▼                              │
│  ┌──────────────────────────────────────────┐                  │
│  │  tasks: dict[int, Task]   (shared state) │                  │
│  └──────────────────────────────────────────┘                  │
│           ▲                                                     │
│  ┌────────┴────────┐                                            │
│  │  render_loop()  │ ─→ LiveWriter ─→ stdout (every 2s)        │
│  └─────────────────┘                                            │
└────────────────────────────────────────────────────────────────┘

main:
  asyncio.gather(
      *[r.run(tasks) for r in runners],
      render_loop(runners, tasks),
  )
```

### Key choices
- **One coroutine per release** — runner reads as straight-line code (`for name in queue: trigger; wait`), achieves real parallelism via `await`.
- **Render loop is independent** — fixed 2s heartbeat. No node coordination required.
- **Shared `tasks: dict[int, Task]` is safe under asyncio** — single-threaded, `await` points are explicit yields. No locks.
- **Termination** — runner is done when its queue is drained and `active_root_id is None`. Whole program ends when all runners done.

## Data Model

```python
@dataclass
class Task:
    id: int
    name: str
    status: str = "Waiting"
    dependency_id: int | None = None
    dependency_name: str | None = None

@dataclass(frozen=True)
class TaskUpdate:
    status: str
    dependency_id: int | None = None
    dependency_name: str | None = None

@dataclass(frozen=True)
class ReleaseTaskDef:
    id: int
    name: str

@dataclass(frozen=True)
class Release:
    id: int
    name: str
    available_tasks: list[ReleaseTaskDef]

@dataclass
class ReleaseRunner:
    release: Release
    trigger_queue: list[str]          # task names yet to trigger
    triggered: list[int]              # task ids already triggered, in order
    active_root_id: int | None = None
    _done: bool = False

    @classmethod
    def from_input(cls, release_name: str, task_names: list[str],
                   releases: list[Release]) -> "ReleaseRunner":
        """Resolve release_name against `releases` metadata.
        Raise ValueError on unknown release_name or any unknown task_name."""

    def is_done(self) -> bool:
        return self._done

    def _resolve_name(self, name: str) -> int:
        """Look up task id from `release.available_tasks`. Raises if missing."""
```

Notes:
- `triggered` doubles as the render-order history. `trigger_queue[len(triggered):]` gives the pending tail to show as `Pending`.
- `Task.dependency_id` chains discovered cascade tasks. The cascade is per-pipeline, not per-runner.

## Mock API

### `mock_api.json` schema

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

### Functions

| Function | Type | Behavior |
|---|---|---|
| `read_mock_api_file()` | `async def -> dict` | Read mock JSON. Async to allow asyncio integration. |
| `get_release_metadata()` | `async def -> list[Release]` | Return all releases with their available task definitions. |
| `get_release_task_info(task_id: int)` | `async def -> dict` | Return status + dep info. Mock: read JSON. |
| `trigger_task(task_id: int)` | `async def -> None` | Mock: write JSON, force the task's status to `InProgress` (idempotent). Prod: HTTP POST to Azure release pipeline. |
| `fetch_task_update(task_id: int)` | `async def -> TaskUpdate` | Wrap `get_release_task_info` with try/except → `TaskUpdate(status="Error")` on failure. |

## Runner Flow

```python
async def run(self, tasks: dict[int, Task]) -> None:
    for name in self.trigger_queue:
        tid = self._resolve_name(name)
        self.active_root_id = tid
        self.triggered.append(tid)
        tasks[tid] = Task(id=tid, name=name)

        try:
            await trigger_task(tid)
        except Exception:
            # Trigger failed — mark Error, skip wait, advance to next queue item.
            tasks[tid].status = "Error"
            self.active_root_id = None
            continue

        await self._wait_chain_terminal(tid, tasks)
        self.active_root_id = None

    self._done = True

async def _wait_chain_terminal(self, root_id, tasks):
    while True:
        await self._poll_chain(root_id, tasks)
        if chain_terminal(root_id, tasks):
            return
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

async def _poll_chain(self, root_id, tasks):
    """Walk root → dep → dep, polling each. Newly discovered deps join `tasks`."""
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

def chain_terminal(root_id: int, tasks: dict[int, Task]) -> bool:
    seen = set()
    current_id = root_id
    while current_id and current_id not in seen:
        seen.add(current_id)
        task = tasks.get(current_id)
        if task is None or not is_terminate_status(task.status):
            return False
        current_id = task.dependency_id
    return True
```

## Render

```python
def render_monitoring(runners: list[ReleaseRunner], tasks: dict[int, Task]) -> str:
    lines = []
    for runner in runners:
        lines.append(f"=== {runner.release.name} ===")
        for tid in runner.triggered:
            root = tasks.get(tid)
            marker = " ◀ active" if tid == runner.active_root_id else ""
            status = root.status if root else "Waiting"
            lines.append(f"  {root.name if root else '?'} : {status}{marker}")
            # cascade chain
            indent = "    "
            current = root
            seen = {tid}
            while current and current.dependency_id and current.dependency_id not in seen:
                seen.add(current.dependency_id)
                dep = tasks.get(current.dependency_id)
                lines.append(f"{indent}|_{current.dependency_name} : {dep.status if dep else 'Waiting'}")
                indent += "  "
                current = dep
        for name in runner.trigger_queue[len(runner.triggered):]:
            lines.append(f"  {name} : Pending")
    return "\n".join(lines)
```

### Example output evolution

```
T0 (just triggered task-a):
=== release-1 ===
  task-a : InProgress ◀ active
  task-c : Pending

T1 (task-a Successed, task-b InProgress):
=== release-1 ===
  task-a : Successed ◀ active
    |_task-b : InProgress
  task-c : Pending

T2 (a+b both Successed, c InProgress):
=== release-1 ===
  task-a : Successed
    |_task-b : Successed
  task-c : InProgress ◀ active
```

## Error Handling

| Scenario | Behavior |
|---|---|
| `trigger_task` API failure | Log; set `Task.status="Error"`; advance to next queue item. |
| `get_release_task_info` failure | `fetch_task_update` returns `TaskUpdate(status="Error")`; runner keeps polling (task may recover). |
| `Error` status — terminal? | **No.** `TERMINATE_STATUSES = {successed, failed, canceled}`. `Error` reflects our observation, not Azure's end state. |
| Unknown task name in `be_trigger_release` | `ReleaseRunner.__init__` raises `ValueError`. Fail fast at startup. |
| Mock JSON read/parse error | Exception bubbles to `main()`; whole program exits. |
| KeyboardInterrupt | `main()` catches, prints `===Cancelled===`, lets LiveWriter cleanup. |
| Trigger on already-running task | Mock: idempotent overwrite. Prod: swallow Azure 409 as "already triggered". |
| Dependency cycle in cascade | `chain_terminal` and `_poll_chain` use `seen` set guards. |
| Cross-release shared task id | Disallowed; design assumes Azure-wide unique task ids. |

## Main Entry

```python
async def main() -> None:
    be_trigger_release: list[tuple[str, list[str]]] = [
        ("release-1", ["task-a", "task-c"]),
    ]

    releases = await get_release_metadata()
    runners = [
        ReleaseRunner.from_input(release_name, task_names, releases)
        for release_name, task_names in be_trigger_release
    ]

    tasks: dict[int, Task] = {}
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

## File Layout

Single `monitor.py`, sectioned:

```
monitor.py
├── Constants & config
├── Data models    (Task, TaskUpdate, ReleaseTaskDef, Release, ReleaseRunner)
├── API layer      (read_mock_api_file, get_release_metadata,
│                   get_release_task_info, trigger_task, fetch_task_update)
├── Polling logic  (poll_task, chain_terminal)
├── Render layer   (render_monitoring, LiveWriter)
└── Entry          (main, render_loop, asyncio.run)
```

If future prod swap-in arrives: API layer splits to `api/mock.py` + `api/azure.py` behind a common `Protocol`. Out of scope for this iteration.

## Testing

Augment `test_monitor.py`:

```python
class ReleaseRunnerTests(IsolatedAsyncioTestCase):
    async def test_runner_processes_queue_sequentially()    # trigger order = [101, 201]
    async def test_runner_waits_for_cascade_chain()          # task-c not triggered until a+b terminal
    async def test_runner_continues_on_failure()             # task-a Failed → still trigger task-c
    async def test_runner_raises_on_unknown_task_name()      # ValueError at construction

class ChainTerminalTests(unittest.TestCase):
    def test_all_terminal_returns_true()
    def test_partial_terminal_returns_false()
    def test_handles_cycle()
    def test_handles_broken_chain_when_dep_missing()
```

Existing tests for `render_monitoring` and `poll_active_tasks` will need updating since `poll_active_tasks` is replaced by the per-runner flow, and `render_monitoring` now takes `runners` instead of `releases`.

## Out of Scope

- Real Azure API integration (still mocked).
- Persistent state across runs (each run starts fresh).
- Cancellation of in-flight tasks via the script (only KeyboardInterrupt handling).
- CLI / config-file input for `be_trigger_release` — hardcoded in `main()` for this iteration.
- Cross-release dependency declarations (each release is independent).
