import asyncio
import json
import sys
import time
from dataclasses import dataclass


TERMINATE_STATUSES = {"successed", "failed", "canceled"}
MOCK_API_FILE = "mock_api.json"
POLL_INTERVAL_SECONDS = 2


@dataclass
class Task:
    """One monitored task with its latest known status and direct dependency."""
    id: int
    name: str
    status: str = "Waiting"
    dependency_id: int | None = None
    dependency_name: str | None = None


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


@dataclass(frozen=True)
class TaskUpdate:
    """A typed snapshot returned from the API. Decouples IO shape from Task fields."""
    status: str
    dependency_id: int | None = None
    dependency_name: str | None = None


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


# MOCK ONLY: read this file on every polling cycle. Edit mock_api.json while the
# monitor is running to simulate API status updates.
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


# MOCK ONLY: replace this function with the real Azure API call in prod.
# Prod function must return the same dict shape:
# {
#     "status": "...",
#     "dependency_task_id": ...,
#     "dependency_task_name": "...",
# }
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


async def trigger_task(task_id) -> None:
    """MOCK ONLY: force the task's status to InProgress. Idempotent.
    In prod, this becomes an HTTP POST to the Azure release pipeline."""
    data = await read_mock_api_file()
    task_data = data["tasks"].get(str(task_id))
    if task_data is None:
        raise KeyError(f"task not found: {task_id}")
    task_data["status"] = "InProgress"
    await _write_mock_api_file(data)


# PROD PORTABLE: can be reused directly.
def is_terminate_status(status):
    """Return True when a task status means monitoring can stop for that task."""
    return status.lower() in TERMINATE_STATUSES


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


# PROD PORTABLE: error handling lives here so callers can stay pure.
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


# PROD PORTABLE: pure mutator — no IO, no error handling.
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


# PROD PORTABLE: can be reused directly.
def render_monitoring(releases: list, tasks: dict) -> str:
    """Render the current monitoring view as terminal text."""
    lines = []

    for release in releases:
        root = tasks.get(release.root_task_id)
        root_status = root.status if root else "Waiting"
        lines.append(f"{release.name} - {release.root_task_name} : {root_status}")

        indent = " " * (len(release.name) + 3)
        seen = {release.root_task_id}
        current = root

        while current and current.dependency_id and current.dependency_name:
            dep_id = current.dependency_id
            dep = tasks.get(dep_id)
            dep_status = dep.status if dep else "Waiting"
            lines.append(f"{indent}|_{current.dependency_name} : {dep_status}")

            if dep_id in seen:
                break
            seen.add(dep_id)
            indent += "  "
            current = dep

    return "\n".join(lines)


# PROD PORTABLE: encapsulates the cursor-line bookkeeping so callers don't.
class LiveWriter:
    """Repaints a multi-line block in place using ANSI cursor moves."""

    def __init__(self):
        self._previous_line_count = 0

    def write(self, output) -> None:
        lines = output.splitlines()
        line_count = max(len(lines), self._previous_line_count)

        if self._previous_line_count:
            sys.stdout.write(f"\x1b[{self._previous_line_count}F")

        for index in range(line_count):
            line = lines[index] if index < len(lines) else ""
            sys.stdout.write(f"\x1b[2K{line}\n")

        sys.stdout.flush()
        self._previous_line_count = len(lines)


# PROD PORTABLE with one prod change: replace release_info with the real
# release/task list source before calling poll_active_tasks().
def main() -> None:
    """Run the monitoring loop until all monitored tasks terminate."""
    tasks: dict = {}
    writer = LiveWriter()
    print("===Start===")

    while True:
        releases = get_release_info()
        poll_active_tasks(releases, tasks)
        writer.write(render_monitoring(releases, tasks))

        if all_tasks_terminated(tasks):
            break

        time.sleep(2)


if __name__ == "__main__":
    main()
