import json
import sys
import time


TERMINATE_STATUSES = {"successed", "failed", "canceled"}
MOCK_API_FILE = "mock_api.json"


# MOCK ONLY: read this file on every polling cycle. Edit mock_api.json while the
# monitor is running to simulate API status updates.
def read_mock_api_file():
    """Read the mock API JSON file used to simulate live status updates."""
    with open(MOCK_API_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


# MOCK ONLY: test input source. In prod, replace this with the release/task list
# returned by your Azure release pipeline query.
def get_release_info():
    """Return initial release tasks from the mock file.

    Returns:
        list[tuple]: Items in (release_id, release_name, task_id, task_name)
        format.
    """
    data = read_mock_api_file()
    return [
        (
            release["release_id"],
            release["release_name"],
            release["task_id"],
            release["task_name"],
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
def get_release_task_info(task_id):
    """Return the latest task status from the mock file.

    Args:
        task_id: Task ID to query.

    Returns:
        dict: A task info mapping with status, dependency_task_id, and
        dependency_task_name.

    Raises:
        KeyError: If the task does not exist in the mock file.
    """
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


# PROD PORTABLE: can be reused if prod get_release_task_info() keeps the same
# return shape.
def poll_task(task_id, task_name, task_cache):
    """Poll one task and update the local task cache.

    A task already in a terminate status is skipped. If the task has a
    dependency task, the dependency is returned so the caller can add it to the
    monitored task set.

    Args:
        task_id: Task ID to poll.
        task_name: Human-readable task name.
        task_cache: Mutable cache storing the latest known task status.

    Returns:
        list[tuple]: Dependency tasks in (task_id, task_name) format.
    """
    if is_terminate_status(task_cache.get(task_id, {}).get("status", "")):
        return []

    try:
        task_info = get_release_task_info(task_id)
    except Exception:
        task_cache[task_id] = {
            "task_name": task_name,
            "status": "Error",
            "dependency_task_id": None,
            "dependency_task_name": None,
        }
        return []

    task_cache[task_id] = {
        "task_name": task_name,
        "status": task_info.get("status", "Unknown"),
        "dependency_task_id": task_info.get("dependency_task_id"),
        "dependency_task_name": task_info.get("dependency_task_name"),
    }

    dependency_task_id = task_info.get("dependency_task_id")
    dependency_task_name = task_info.get("dependency_task_name")
    if dependency_task_id and dependency_task_name:
        return [(dependency_task_id, dependency_task_name)]

    return []


# PROD PORTABLE: can be reused if releases keep the same tuple shape:
# (rls_id, rls_name, task_id, task_name).
def poll_active_tasks(releases, task_cache, monitored_tasks):
    """Poll all active tasks and newly discovered dependency tasks.

    Initial release tasks are added to monitored_tasks first. Dependency tasks
    found during polling are queried in the same polling cycle.

    Args:
        releases: Release task tuples in (release_id, release_name, task_id, task_name) format.
        task_cache: Mutable cache storing latest task info by task ID.
        monitored_tasks: Mutable mapping of task ID to task name.
    """
    for _, _, task_id, task_name in releases:
        monitored_tasks.setdefault(task_id, task_name)

    pending_tasks = list(monitored_tasks.items())
    polled_tasks = set()

    while pending_tasks:
        task_id, task_name = pending_tasks.pop(0)
        if task_id in polled_tasks:
            continue

        polled_tasks.add(task_id)
        dependencies = poll_task(task_id, task_name, task_cache)
        for dependency_task_id, dependency_task_name in dependencies:
            if dependency_task_id not in monitored_tasks:
                monitored_tasks[dependency_task_id] = dependency_task_name
                pending_tasks.append((dependency_task_id, dependency_task_name))


# PROD PORTABLE: can be reused directly.
def render_monitoring(releases, task_cache):
    """Render the current monitoring view as terminal text.

    Args:
        releases: Release task tuples in
        (release_id, release_name, task_id, task_name) format.
        task_cache: Latest known task info by task ID.

    Returns:
        str: Multi-line terminal output.
    """
    lines = ["===== Monitoring ====="]

    for _, release_name, task_id, task_name in releases:
        task_info = task_cache.get(task_id, {})
        status = task_info.get("status", "Waiting")

        lines.append(f"{release_name} - {task_name} : {status}")

        dependency_task_id = task_info.get("dependency_task_id")
        dependency_task_name = task_info.get("dependency_task_name")
        if dependency_task_id and dependency_task_name:
            dependency_status = task_cache.get(dependency_task_id, {}).get("status", "Waiting")
            indent = " " * (len(release_name) + 3)
            lines.append(f"{indent}|_{dependency_task_name} : {dependency_status}")

    return "\n".join(lines)


# PROD PORTABLE: can be reused directly for realtime terminal updates without
# cls/clear.
def write_live_update(output, previous_line_count):
    """Write a realtime terminal update without clearing the full terminal.

    The function moves the cursor back to the beginning of the previous output
    block, clears each old line, and writes the new block.

    Args:
        output: New multi-line output to display.
        previous_line_count: Number of lines written by the previous update.

    Returns:
        int: Number of lines written by this update.
    """
    lines = output.splitlines()
    line_count = max(len(lines), previous_line_count)

    if previous_line_count:
        sys.stdout.write(f"\x1b[{previous_line_count}F")

    for index in range(line_count):
        line = lines[index] if index < len(lines) else ""
        sys.stdout.write(f"\x1b[2K{line}\n")

    sys.stdout.flush()
    return len(lines)


# PROD PORTABLE: can be reused directly.
def all_tasks_terminated(task_cache, monitored_tasks):
    """Return True when every monitored task has reached a terminate status."""
    if not monitored_tasks:
        return False

    for task_id in monitored_tasks:
        status = task_cache.get(task_id, {}).get("status", "")
        if not is_terminate_status(status):
            return False

    return True


# PROD PORTABLE with one prod change: replace release_info with the real
# release/task list source before calling poll_active_tasks().
def main():
    """Run the monitoring loop until all monitored tasks terminate."""
    task_cache = {}
    monitored_tasks = {}
    previous_line_count = 0
    print("===Start===")

    while True:
        release_info = get_release_info()
        poll_active_tasks(release_info, task_cache, monitored_tasks)
        output = render_monitoring(release_info, task_cache)
        previous_line_count = write_live_update(output, previous_line_count)

        if all_tasks_terminated(task_cache, monitored_tasks):
            break

        time.sleep(2)


if __name__ == "__main__":
    main()
