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
