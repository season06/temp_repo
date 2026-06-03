import json
import sys
import time
from dataclasses import dataclass


TERMINATE_STATUSES = {"successed", "failed", "canceled"}
MOCK_API_FILE = "mock_api.json"


@dataclass
class Task:
    """One monitored task with its latest known status and direct dependency."""
    id: int
    name: str
    status: str = "Waiting"
    dependency_id: int | None = None
    dependency_name: str | None = None


@dataclass(frozen=True)
class Release:
    """A release entry pointing at its root task."""
    id: int
    name: str
    root_task_id: int
    root_task_name: str


@dataclass(frozen=True)
class TaskUpdate:
    """A typed snapshot returned from the API. Decouples IO shape from Task fields."""
    status: str
    dependency_id: int | None = None
    dependency_name: str | None = None


# MOCK ONLY: read this file on every polling cycle. Edit mock_api.json while the
# monitor is running to simulate API status updates.
def read_mock_api_file() -> dict:
    """Read the mock API JSON file used to simulate live status updates."""
    with open(MOCK_API_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


# MOCK ONLY: test input source. In prod, replace this with the release/task list
# returned by your Azure release pipeline query.
def get_release_info() -> list:
    """Return the initial release/root-task list."""
    data = read_mock_api_file()
    return [
        Release(
            id=release["release_id"],
            name=release["release_name"],
            root_task_id=release["task_id"],
            root_task_name=release["task_name"],
        )
        for release in data["releases"]
    ]


# MOCK ONLY: replace this function with the real Azure API call in prod.
# Prod function must return the same dict shape:
# {
#     "status": "...",
#     "dependency_task_id": ...,
#     "dependency_task_name": "...",
# }
def get_release_task_info(task_id) -> dict:
    """Return the latest task status from the mock file."""
    data = read_mock_api_file()
    task_data = data["tasks"].get(str(task_id))

    if task_data is None:
        raise KeyError(f"task not found: {task_id}")

    return {
        "status": task_data.get("status", "Unknown"),
        "dependency_task_id": task_data.get("dependency_task_id"),
        "dependency_task_name": task_data.get("dependency_task_name"),
    }


# PROD PORTABLE: can be reused directly.
def is_terminate_status(status):
    """Return True when a task status means monitoring can stop for that task."""
    return status.lower() in TERMINATE_STATUSES


# PROD PORTABLE: error handling lives here so callers can stay pure.
def fetch_task_update(task_id) -> TaskUpdate:
    """Fetch latest task state via the API. Return an Error update if the call fails."""
    try:
        info = get_release_task_info(task_id)
    except Exception:
        return TaskUpdate(status="Error")
    return TaskUpdate(
        status=info.get("status", "Unknown"),
        dependency_id=info.get("dependency_task_id"),
        dependency_name=info.get("dependency_task_name"),
    )


# PROD PORTABLE: pure mutator — no IO, no error handling.
def poll_task(task):
    """Apply the latest update to a task. Return the newly discovered dependency, if any."""
    if is_terminate_status(task.status):
        return None

    update = fetch_task_update(task.id)
    task.status = update.status
    task.dependency_id = update.dependency_id
    task.dependency_name = update.dependency_name

    if update.dependency_id and update.dependency_name:
        return Task(id=update.dependency_id, name=update.dependency_name)

    return None


# PROD PORTABLE.
def poll_active_tasks(releases: list, tasks: dict) -> None:
    """Poll all active tasks and newly discovered dependency tasks.

    `tasks` is the single source of truth — it doubles as the known-task set and
    the status store. New dependency tasks discovered during polling are appended
    to the worklist within the same cycle.
    """
    for release in releases:
        tasks.setdefault(
            release.root_task_id,
            Task(id=release.root_task_id, name=release.root_task_name),
        )

    worklist = list(tasks.values())
    while worklist:
        task = worklist.pop()
        new_dep = poll_task(task)
        if new_dep and new_dep.id not in tasks:
            tasks[new_dep.id] = new_dep
            worklist.append(new_dep)


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


# PROD PORTABLE: can be reused directly.
def all_tasks_terminated(tasks: dict) -> bool:
    """Return True when every monitored task has reached a terminate status."""
    if not tasks:
        return False
    return all(is_terminate_status(task.status) for task in tasks.values())


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
