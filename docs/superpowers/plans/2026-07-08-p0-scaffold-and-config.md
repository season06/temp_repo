# P0 — 骨架與環境 (Scaffold & Config) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 `agent_template` 套件骨架、可運作的 `.venv` 環境與相依套件,並實作 `AgentConfig` 與 runtime `Config` 兩個設定類別。

**Architecture:** 單一 top-level package `agent_template/`,設定拆成兩個檔案：`config.py` 承載 `AgentConfig`（每個 agent 的 LLM 設定）與 `Config`（runtime：auth 端點 + Observability）。測試放 `tests/`（本身是 package,免 editable install,從 repo 根目錄跑 pytest 即可 import）。

**Tech Stack:** Python 3.14、deepagents 0.6.12、langchain-openai 1.3.3、pytest、hatchling（build backend）。

## Global Constraints

- **Python 環境**：系統 Python 3.14 為 externally-managed，且 `venv` 無 pip/ensurepip。建立 venv 用 `python3 -m venv --without-pip .venv`；安裝套件一律用 host pip 指向 venv：`python3 -m pip --python .venv/bin/python install <pkg>`（`--python` 必須放在 `install` 之前）。**不要**在 venv 內直接跑 `pip install`。
- **相依版本（已在既有專案驗證,務必 pin）**：`deepagents==0.6.12`、`langchain-openai==1.3.3`。
- **執行測試**：一律 `.venv/bin/python -m pytest`（在 repo 根目錄執行）。
- **型別註記慣例**：只在 `dict` / `list` 上標註型別；不 import `typing`、不標註 primitive（str/int/float/bool）。設定類別用**普通 class + `__init__`**,不用 dataclass（以免被迫標註 primitive）。
- **Commit 時機**：本計畫在執行階段才會 commit；由使用者決定何時執行此計畫。每個 Task 結尾的 commit 步驟屬執行期動作。

---

### Task 1: 專案骨架、venv 與相依安裝

**Files:**
- Create: `pyproject.toml`
- Create: `agent_template/__init__.py`
- Create: `tests/__init__.py`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: 無（起始 Task）。
- Produces: `agent_template.__version__`（字串 `"0.1.0"`）— 後續 Task 與 phase 以 `import agent_template` 為可用性前提。

- [ ] **Step 1: 建立 package 目錄與空檔**

```bash
cd /home/xizhen/文件/temp_repo
mkdir -p agent_template tests docs/superpowers/plans
touch agent_template/__init__.py tests/__init__.py
```

- [ ] **Step 2: 寫 `pyproject.toml`**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agent-template"
version = "0.1.0"
description = "Framework-agnostic AI Agent SDK (MVP)"
requires-python = ">=3.14"
dependencies = [
    "deepagents==0.6.12",
    "langchain-openai==1.3.3",
]

[tool.hatch.build.targets.wheel]
packages = ["agent_template"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: 建立 venv 並用 host pip 安裝相依**

```bash
cd /home/xizhen/文件/temp_repo
python3 -m venv --without-pip .venv
python3 -m pip --python .venv/bin/python install deepagents==0.6.12 langchain-openai==1.3.3 pytest
```

Expected: 安裝成功結束（`Successfully installed ... deepagents-0.6.12 ... langchain-openai-1.3.3 ... pytest-...`）。

- [ ] **Step 4: 驗證相依可 import**

```bash
cd /home/xizhen/文件/temp_repo
.venv/bin/python -c "import deepagents, langchain_openai; print('deps-ok')"
```

Expected: 輸出 `deps-ok`。

- [ ] **Step 5: 寫 smoke test（會失敗）**

Create `tests/test_smoke.py`:

```python
import agent_template


def test_package_imports_with_version():
    assert agent_template.__version__ == "0.1.0"
```

- [ ] **Step 6: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_smoke.py -v`
Expected: FAIL — `AttributeError: module 'agent_template' has no attribute '__version__'`。

- [ ] **Step 7: 在 `__init__.py` 加入版號**

Write `agent_template/__init__.py`:

```python
__version__ = "0.1.0"
```

- [ ] **Step 8: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_smoke.py -v`
Expected: PASS（1 passed）。

- [ ] **Step 9: 加入 `.gitignore` 並 commit**

Create `.gitignore`:

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
```

```bash
cd /home/xizhen/文件/temp_repo
git add pyproject.toml agent_template/__init__.py tests/__init__.py tests/test_smoke.py .gitignore
git commit -m "chore: scaffold agent_template package and venv"
```

---

### Task 2: `AgentConfig`（每個 agent 的 LLM 設定）

**Files:**
- Create: `agent_template/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: 無。
- Produces: `AgentConfig(api_key, base_url, model, temperature=0.0, system_prompt=None)`，屬性同名。P1 的 `build_agent` 消費此類別。

- [ ] **Step 1: 寫 `AgentConfig` 的測試（會失敗）**

Create `tests/test_config.py`:

```python
from agent_template.config import AgentConfig


def test_agent_config_holds_required_fields():
    cfg = AgentConfig(api_key="k", base_url="http://localhost/v1", model="qwen")
    assert cfg.api_key == "k"
    assert cfg.base_url == "http://localhost/v1"
    assert cfg.model == "qwen"


def test_agent_config_defaults():
    cfg = AgentConfig(api_key="k", base_url="b", model="m")
    assert cfg.temperature == 0.0
    assert cfg.system_prompt is None


def test_agent_config_overrides():
    cfg = AgentConfig(api_key="k", base_url="b", model="m", temperature=0.3, system_prompt="SP")
    assert cfg.temperature == 0.3
    assert cfg.system_prompt == "SP"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_template.config'`。

- [ ] **Step 3: 實作 `AgentConfig`**

Create `agent_template/config.py`:

```python
class AgentConfig:
    """單一 agent 的 LLM 設定（OpenAI-compatible 端點）。"""

    def __init__(self, api_key, base_url, model, temperature=0.0, system_prompt=None):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.system_prompt = system_prompt
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 5: Commit**

```bash
cd /home/xizhen/文件/temp_repo
git add agent_template/config.py tests/test_config.py
git commit -m "feat: add AgentConfig for OpenAI-compatible LLM settings"
```

---

### Task 3: runtime `Config`（auth + Observability）與 `from_env`

**Files:**
- Modify: `agent_template/config.py`
- Test: `tests/test_config.py:1-...`（同檔追加）

**Interfaces:**
- Consumes: 無。
- Produces: `Config(auth_endpoint=None, otel_endpoint=None, sampling_ratio=1.0, o11y_enabled=True, cid=None, agent_version=None)`，屬性同名；classmethod `Config.from_env()` 從環境變數載入。P4（auth）與 P5（o11y）消費此類別。

環境變數對應：`AGENT_AUTH_ENDPOINT`、`AGENT_OTEL_ENDPOINT`、`AGENT_OTEL_SAMPLING_RATIO`、`AGENT_O11Y_ENABLED`、`AGENT_CID`、`AGENT_VERSION`。

- [ ] **Step 1: 寫 `Config` 的測試（會失敗）**

Append to `tests/test_config.py`:

```python
from agent_template.config import Config


def test_config_defaults():
    cfg = Config()
    assert cfg.auth_endpoint is None
    assert cfg.otel_endpoint is None
    assert cfg.sampling_ratio == 1.0
    assert cfg.o11y_enabled is True
    assert cfg.cid is None
    assert cfg.agent_version is None


def test_config_from_env_reads_values(monkeypatch):
    monkeypatch.setenv("AGENT_AUTH_ENDPOINT", "http://auth/verify")
    monkeypatch.setenv("AGENT_OTEL_ENDPOINT", "http://collector:4317")
    monkeypatch.setenv("AGENT_OTEL_SAMPLING_RATIO", "0.5")
    monkeypatch.setenv("AGENT_O11Y_ENABLED", "false")
    monkeypatch.setenv("AGENT_CID", "proj-123")
    monkeypatch.setenv("AGENT_VERSION", "1.2.3")
    cfg = Config.from_env()
    assert cfg.auth_endpoint == "http://auth/verify"
    assert cfg.otel_endpoint == "http://collector:4317"
    assert cfg.sampling_ratio == 0.5
    assert cfg.o11y_enabled is False
    assert cfg.cid == "proj-123"
    assert cfg.agent_version == "1.2.3"


def test_config_from_env_uses_defaults_when_unset(monkeypatch):
    for key in ("AGENT_AUTH_ENDPOINT", "AGENT_OTEL_ENDPOINT", "AGENT_OTEL_SAMPLING_RATIO",
                "AGENT_O11Y_ENABLED", "AGENT_CID", "AGENT_VERSION"):
        monkeypatch.delenv(key, raising=False)
    cfg = Config.from_env()
    assert cfg.auth_endpoint is None
    assert cfg.sampling_ratio == 1.0
    assert cfg.o11y_enabled is True
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'Config'`。

- [ ] **Step 3: 實作 `Config` 與 `from_env`**

Append to `agent_template/config.py`:

```python
import os


class Config:
    """SDK runtime 設定：auth 端點與 Observability。"""

    def __init__(self, auth_endpoint=None, otel_endpoint=None, sampling_ratio=1.0,
                 o11y_enabled=True, cid=None, agent_version=None):
        self.auth_endpoint = auth_endpoint
        self.otel_endpoint = otel_endpoint
        self.sampling_ratio = sampling_ratio
        self.o11y_enabled = o11y_enabled
        self.cid = cid
        self.agent_version = agent_version

    @classmethod
    def from_env(cls):
        ratio = os.environ.get("AGENT_OTEL_SAMPLING_RATIO")
        enabled = os.environ.get("AGENT_O11Y_ENABLED")
        return cls(
            auth_endpoint=os.environ.get("AGENT_AUTH_ENDPOINT"),
            otel_endpoint=os.environ.get("AGENT_OTEL_ENDPOINT"),
            sampling_ratio=float(ratio) if ratio is not None else 1.0,
            o11y_enabled=(enabled.lower() != "false") if enabled is not None else True,
            cid=os.environ.get("AGENT_CID"),
            agent_version=os.environ.get("AGENT_VERSION"),
        )
```

Put the `import os` at the top of `config.py`（移到檔案最上方,不要留在類別中間）。

- [ ] **Step 4: 跑全部測試確認通過**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS（smoke 1 + AgentConfig 3 + Config 3 = 7 passed）。

- [ ] **Step 5: Commit**

```bash
cd /home/xizhen/文件/temp_repo
git add agent_template/config.py tests/test_config.py
git commit -m "feat: add runtime Config with from_env loader"
```

---

## Self-Review

- **Spec coverage**：本 phase 對應 req.md「Config」段落（LLM / auth / o11y 欄位 config 化）與套件散布骨架。`AgentConfig` 涵蓋 api_key/base_url/model/temperature/system_prompt；`Config` 涵蓋 auth_endpoint 與 o11y 五欄。✅
- **Placeholder scan**：無 TBD/TODO;所有測試與實作皆為具體程式碼。✅
- **Type consistency**：`AgentConfig` 欄位名（api_key/base_url/model/temperature/system_prompt）與 `Config` 欄位名（auth_endpoint/otel_endpoint/sampling_ratio/o11y_enabled/cid/agent_version）在測試與實作一致,P1 將以相同名稱消費。✅
