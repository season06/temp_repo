# Design: deepagents demo → Nuitka `.so` → wheel → GitLab CI

Date: 2026-07-06

## Goal

A minimal `deepagents` program that is compiled by **Nuitka** into a `.so`, that
`.so` is packaged into a **wheel** (source `.py` excluded), and the whole flow is
driven by **uv** inside `.gitlab-ci.yml`. Verification: install the wheel in a
clean environment and `import` it successfully.

## Decisions

- **Single-file module** `agent_demo.py` (not a multi-file package). Nuitka
  `--module` compiles one file cleanly into one importable `.so`; avoids the
  fragile "embed submodules into one `.so`" path.
- **Offline agent.** Uses a fake LangChain chat model — no network, no API key —
  so CI compile/package/verify never needs secrets.
- **Only our code is compiled.** `deepagents` stays a normal pip runtime
  dependency declared in the wheel; Nuitka scope is just `agent_demo.py`.
- **Target:** Python 3.14 / linux_x86_64. The wheel is a platform wheel tagged
  `cp314-cp314-linux_x86_64` — good for this demo, not for PyPI.
- **uv-managed Python.** Built with `UV_PYTHON_PREFERENCE=only-managed` so the
  interpreter bundles `Python.h`; the distro's `python3.14` lacked dev headers
  and Nuitka's C compile failed against it.

## Components

| File | Purpose |
|------|---------|
| `agent_demo.py` | The deepagent + one `add` tool + `run()` / `main()`. Compiled to `.so`. |
| `pyproject.toml` | hatchling backend; `only-include = ["build"]` drops the source `.py`; a custom build hook adds the `.so`; deps = `deepagents`; dev = `nuitka`, `build`. |
| `hatch_build.py` | Build hook: globs `build/agent_demo.cpython-*.so`, force-includes it, sets `pure_python=false`/`infer_tag=true` for the platform tag. |
| `verify_import.py` | Smoke test: import installed `agent_demo`, assert Nuitka loader + on-disk `.so` (no `.py`), run the agent. |
| `.gitlab-ci.yml` | `build` (uv sync → nuitka → build wheel) and `verify` (clean install + import) stages. |

## Pipeline

1. `uv sync --no-install-project` — install `deepagents` + `nuitka` + `build`.
2. `uv run --no-sync python -m nuitka --module agent_demo.py --output-dir=build`
   → `build/agent_demo.cpython-314-*.so`.
3. `uv run --no-sync python -m build --wheel` — the build hook globs the `.so`,
   force-includes it, and sets the tag → `dist/agent_demo-0.1.0-cp314-cp314-linux_x86_64.whl`
   (no rename, no separate retag step).
4. Verify: fresh uv venv → install wheel (pulls `deepagents`) → run
   `verify_import.py` from a directory with no `agent_demo.py`.

## Success criteria (all verified locally)

- Wheel contains `agent_demo.so`, not `agent_demo.py`. ✓
- Installed module's loader is `nuitka_module_loader` and `agent_demo.run()`
  returns a non-empty string offline. ✓
- Pipeline runs green end-to-end. ✓ (local)

## Notes / gotchas learned

- `create_deep_agent(tools=..., system_prompt=..., model=...)` — confirmed working
  on the installed deepagents.
- The offline fake model must implement `bind_tools` (the agent stack calls it);
  `GenericFakeChatModel` doesn't, so `agent_demo.py` subclasses it.
- Nuitka sets a compiled module's `__file__`/`__spec__.origin` to a synthetic
  `.py`; verify compilation via `__loader__` + the on-disk `.so`.
- Nuitka forbids renaming an extension module (`--output-filename` errors for
  `--module`), so the `.so` keeps its `cpython-<ver>-<plat>` name. hatchling's
  `only-include`/`force-include` only bypass `.gitignore` for an *exact existing
  file path* (not a dir or glob), so a build hook globs the real name instead of
  hard-coding it — this also lets the hook set the platform tag directly, giving
  `Root-Is-Purelib: false` with no separate `wheel tags` retag.
