# Azure Flow Integration — Design Spec

**Date:** 2026-06-05
**Status:** Approved, awaiting implementation plan
**Author:** brainstormed with user
**Builds on:** `2026-06-04-release-task-orchestrator-design.md`

## Goal

Complete the end-to-end flow **from finding a release definition to triggering its
tasks**, and combine it with the existing `monitor.py` orchestrator.

`main.py` becomes the entry point: it owns the Azure DevOps REST API layer (real
request shapes, with the single network call left as a clearly-marked stub), the
interactive CLI flow, and the wiring into `monitor.py`. `monitor.py` becomes a
reusable orchestration library that runs against an **injected API seam**, so the
same `ReleaseRunner` / `render_loop` machinery works against either the mock
(`mock_api.json`) or Azure.

This is the iteration that pulls in two items the prior spec listed as out of
scope: *real Azure API integration* (here: real shapes, stubbed HTTP) and *CLI
input for `be_trigger_release`*.

## Decisions (resolved during brainstorming)

1. **API backing:** Real Azure REST *structure* (URLs, auth headers, payloads),
   with the actual network call isolated to one fill-in point. Not yet live.
2. **Integration:** Inject the Azure API into `monitor.py` via a small seam.
   `ReleaseRunner`'s trigger/poll go through the injected `api`. One unified,
   Azure-shaped pipeline driven by `main.py`.
3. **Task model:** A monitored "task" maps to an Azure release **environment /
   stage**. `available_tasks` = the release's environments; trigger = set
   environment status `inProgress`; poll = environment status.

## Architecture

```
main.py (entry point)
  ├─ argparse: --pat   (org / project / api-version are module-level constants)
  ├─ Azure API layer (real REST shapes; ONE stubbed HTTP call: _send_request)
  ├─ interactive flow: find → select → create → select tasks
  └─ AzureApi(seam) ──────────────┐
                                   ▼
monitor.py (reusable library)   run_orchestration(runners, tasks, api, writer)
  ├─ ReleaseRunner.run(tasks, api)      ← trigger/poll go through `api`
  ├─ poll_task / fetch_task_update      ← take `api`
  ├─ render_loop / LiveWriter / render_monitoring / chain_terminal  (unchanged)
  └─ MockApi(seam)  ← used by monitor.monitor() offline demo + tests
```

### Key choices

- **API seam is the combine point.** The only coupling between `main.py` and
  `monitor.py`'s runtime is a two-method interface. Everything else
  (`render_*`, `LiveWriter`, `chain_terminal`) stays pure and untouched.
- **`main.py` owns metadata construction.** Release/environment objects are built
  in `main.py` from `get_release`, so the seam only needs the two *runtime*
  operations (trigger + poll), not metadata fetching.
- **Offline demo preserved.** `monitor.monitor()` keeps working via `MockApi`;
  the Azure path is the new `main.py` entry.

## The API seam

A tiny interface with the two runtime operations `ReleaseRunner` needs:

```python
class Api:                                    # structural; no ABC required
    async def trigger_task(self, release_id, task_id) -> None: ...
    async def get_task_info(self, release_id, task_id, task_name) -> dict: ...
```

`get_task_info` returns the existing dict shape:

```python
{"status": "...", "dependency_task_id": ... | None, "dependency_task_name": ... | None}
```

### MockApi (in monitor.py)

Wraps the existing `mock_api.json` helpers:

- `trigger_task` → existing `trigger_task` module function (force `InProgress`).
- `get_task_info` → existing `get_release_task_info` module function.

Keeps `monitor.monitor()` and the test suite runnable offline.

### AzureApi (in main.py)

Wraps the Azure REST functions, holding `pat`, `org`, `project`, `api_version`:

- `trigger_task(release_id, task_id)` → `trigger_release_task(...)` (PATCH env → `inProgress`).
- `get_task_info(release_id, task_id, task_name)` → derive status + cascade from
  `get_release(...)` environment data, returned in the dict shape above.

## monitor.py changes

`ReleaseRunner` and the polling functions stop calling module-level API
functions and take `api` as a parameter instead:

```python
async def run(self, tasks, api) -> None: ...
async def _wait_chain_terminal(self, root_id, tasks, api) -> None: ...
async def _poll_chain(self, root_id, tasks, api) -> None: ...           # poll_task(task, release_id, api)

async def poll_task(task, release_id, api): ...                         # update via api.get_task_info
async def fetch_task_update(api, release_id, task_id, task_name) -> TaskUpdate: ...
```

New reusable orchestration entry (extracted from `monitor()`):

```python
async def run_orchestration(runners, tasks, api, writer) -> None:
    await asyncio.gather(
        *(r.run(tasks, api) for r in runners),
        render_loop(runners, tasks, writer),
    )
```

`monitor.monitor()` is rewritten to build a `MockApi` + mock `Release` objects
and call `run_orchestration`. `chain_terminal`, `render_monitoring`,
`render_loop`, `LiveWriter` are unchanged.

Per the project convention, new primitive params are left unannotated; only
`dict` / `list` are annotated.

## Azure REST layer (main.py)

Base host: `https://vsrm.dev.azure.com/{ORG}/{PROJECT}/_apis/release`, where
`ORG`, `PROJECT`, and `API_VERSION` (default `7.1`) are **module-level constants**
at the top of `main.py`. Only `--pat` is a CLI argument.
Auth: `Authorization: Basic base64(":" + pat)`.

| Function | Method + path | Body | Returns |
|---|---|---|---|
| `find_release_definition(pat, definition_name)` | `GET /definitions?searchText={name}` | — | `list` of `(name, id)`, fuzzy-filtered |
| `create_release(pat, definition_id)` | `POST /releases` | `{"definitionId": id}` | `int` release id |
| `get_release(pat, release_id)` | `GET /releases/{id}` | — | `dict` incl. `name`, `environments[]` |
| `trigger_release_task(pat, release_id, environment_id)` | `PATCH /releases/{id}/environments/{envId}` | `{"status": "inProgress"}` | `dict` env details |

### The single stubbed HTTP point

```python
def _send_request(method, url, pat, body=None) -> dict:
    """The ONE network call. Builds the PAT basic-auth header for real;
    the actual HTTP send is the fill-in point for prod."""
    headers = {"Authorization": _basic_auth(pat), "Content-Type": "application/json"}
    raise NotImplementedError("wire real HTTP here (e.g. requests.request / urllib)")
```

Everything above this — URL construction, query params, JSON bodies, auth header,
response shaping — is real and unit-testable by patching `_send_request`.

`_basic_auth(pat)` = `"Basic " + base64(b":" + pat)` (stdlib `base64`).

## Interactive flow (main)

`main()` parses args, runs the synchronous interactive steps, then hands off to
the async orchestration via `asyncio.run`.

0. Prompt for release-definition search text.
1. `find_release_definition(pat, text)` → numbered list → prompt user to pick one
   or more (comma-separated indices). Re-prompt on empty/invalid.
2. `create_release(pat, definition_id)` for each pick → release id.
3. `get_release(pat, release_id)` → list environments (tasks) → prompt user to
   pick tasks to execute per release (comma-separated). Re-prompt on invalid.
4. Build `be_trigger_release` + `Release`/`ReleaseRunner` objects + `AzureApi`,
   then `asyncio.run(run_orchestration(runners, tasks, api, writer))`.

Selection parsing (`"1,3"` → indices) and fuzzy matching are small pure helpers,
unit-tested independently of I/O.

## Error handling

| Scenario | Behavior |
|---|---|
| Trigger failure (`api.trigger_task` raises) | Existing: set `Task.status="Error"`, advance to next queue item. |
| Poll failure (`api.get_task_info` raises) | Existing: `fetch_task_update` → `TaskUpdate(status="Error")`; keep polling. |
| Azure HTTP error | Surfaces from `_send_request`; offline/mock path never reaches it. |
| Empty / invalid CLI selection | Re-prompt; do not crash. |
| Unknown task/release name | `ReleaseRunner.from_input` raises `ValueError` (fail fast). |
| Missing `--pat` | argparse error at startup. |

## Testing

**`test_monitor.py` (update):** replace the `patch.object(monitor,
"fetch_task_update", ...)` pattern with a small `FakeApi` whose `get_task_info` /
`trigger_task` return scripted values, passed into `run` / `poll_task` /
`_poll_chain`. Coverage of sequential triggering, cascade waiting, and
failure-advance is preserved.

**`test_main.py` (new):**
- Fuzzy matching of release-definition search text.
- Selection-string parsing (`"1,3"`, whitespace, out-of-range, empty).
- Azure request **shaping**: each function builds the correct method / URL / body
  / auth header, verified by patching `_send_request`.
- `AzureApi.get_task_info` maps an environment payload to the status dict shape.

## File layout

```
main.py
├── Constants (ORG, PROJECT, API_VERSION, host template, status literals)
├── Azure API layer (_basic_auth, _send_request, find/create/get/trigger)
├── AzureApi (seam adapter)
├── Interactive helpers (fuzzy match, parse selection)
└── main() entry  (argparse → interactive → asyncio.run(run_orchestration))

monitor.py
├── (unchanged) data models, render layer, chain_terminal, LiveWriter
├── MockApi (seam adapter over mock_api.json)
├── ReleaseRunner / poll_task / fetch_task_update  (now take `api`)
├── run_orchestration(runners, tasks, api, writer)
└── monitor()  (offline demo via MockApi)
```

## Out of scope

- Real HTTP wiring inside `_send_request` (left as the fill-in point).
- PAT/token refresh, retries, pagination of definition search results.
- Persistent state across runs; cancelling in-flight environments.
- Cross-release dependency declarations.
