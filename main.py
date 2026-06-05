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


def create_release(pat, definition_id) -> int:
    """Create a new release from a definition. Returns the created release id."""
    url = f"{RELEASE_HOST}/releases?api-version={API_VERSION}"
    data = _send_request("POST", url, pat, {"definitionId": definition_id})
    return data["id"]


def get_release(pat, release_id) -> dict:
    """Get release detail including environments. Returns the release JSON."""
    url = f"{RELEASE_HOST}/releases/{release_id}?api-version={API_VERSION}"
    return _send_request("GET", url, pat)


def trigger_release_task(pat, release_id, environment_id) -> dict:
    """Trigger a release task by setting its environment status to inProgress.
    Returns the updated environment JSON."""
    url = f"{RELEASE_HOST}/releases/{release_id}/environments/{environment_id}?api-version={API_VERSION}"
    return _send_request("PATCH", url, pat, {"status": "inProgress"})


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
