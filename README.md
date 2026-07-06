# agent-demo

A minimal [`deepagents`](https://pypi.org/project/deepagents/) program that is
compiled with **Nuitka** into a `.so` and shipped as a **wheel**, all driven by
**uv**. The agent runs fully offline (fake chat model — no API key).

## Layout

| File | Purpose |
|------|---------|
| `agent_demo.py` | The deep agent + an `add` tool. Compiled to a `.so`. |
| `pyproject.toml` | hatchling build; packages the `.so` into a platform wheel. |
| `hatch_build.py` | Build hook: globs the Nuitka `.so` into the wheel + sets the platform tag. |
| `verify_import.py` | Installs-and-imports smoke test. |
| `.gitlab-ci.yml` | `build` + `verify` pipeline. |

## Local build (needs uv + a C compiler like gcc)

```bash
uv sync --no-install-project     # deepagents + nuitka + build (Python 3.14)
uv run --no-sync python -m nuitka --module agent_demo.py --output-dir=build --assume-yes-for-downloads
uv run --no-sync python -m build --wheel
ls dist/          # agent_demo-0.1.0-cp314-cp314-linux_x86_64.whl
```

The build hook `hatch_build.py` globs `build/agent_demo.cpython-*.so`, adds it to
the wheel, and sets the platform tag — so there's no rename step and no wheel
retag step.

> Use uv-managed Python (`UV_PYTHON_PREFERENCE=only-managed`) — it bundles the
> `Python.h` headers Nuitka needs; a bare distro python often lacks them.

## Verify

```bash
uv venv /tmp/verify --python 3.14
uv pip install --python /tmp/verify/bin/python dist/*.whl
cp verify_import.py /tmp/ && cd /tmp && /tmp/verify/bin/python verify_import.py
```

Expected: `OK: compiled wheel imports and runs`.

> The wheel contains `agent_demo.so`, not the source `.py`. Nuitka reports the
> module's `__file__` as a synthetic `.py`, so the check uses `__loader__`
> (`nuitka_module_loader`) and the on-disk `.so` instead.
