# P1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 `agent_template` 套件骨架與基礎建構流程,讓成員能用單一 `build_agent()` 入口跑出最小可用的 deepagents agent(尚無安全外殼,P2 加入)。

**Architecture:** 純 Python 套件。`build_agent()` 為唯一入口,讀取 `AgentConfig`,經 `providers` 建立 Qwen(OpenAI 相容)chat model,再呼叫 deepagents 建出 agent。安全外殼在 factory 中預留接縫(P1 僅 `instructions = task_prompt`),P2 接管。

**Tech Stack:** Python 3.11+、deepagents、langchain-openai、langgraph、pytest。

## Global Constraints

- Python 版本下限:3.11(設定檔與型別語法以此為準)。
- 型別註記規則:一般模組只在參數/回傳為 `dict` / `list` 時加註;不 import `typing`、不註記原始型別。**例外:** `config.py` 用全型別 frozen dataclass(`from __future__ import annotations`、`int` / `str | None` / `float` / `bool`、`__post_init__` 驗證回 `-> None`)。
- 對外公開介面僅由 `agent_template/__init__.py` 匯出;私有模組(底線開頭)不對外。
- LLM provider:Qwen,走 OpenAI 相容 `/chat/completions`(`base_url` + `api_key` + `model`),非本地模型。
- 安全外殼(prompt 夾心 / 輸入防護 / 輸出驗證)**不在 P1 範圍**;P1 只建立可被 P2 接手的接縫。
- **執行環境:** 相依套件已安裝於專案根目錄的 `.venv`(deepagents 0.6.12、langchain-openai 1.3.3、langgraph)。所有測試以 **`.venv/bin/python -m pytest`** 於 repo 根目錄執行;**不要**用裸 `pytest`,也**不要**跑 `pip install`(此環境為 externally-managed,venv 內無 pip)。`tests/` 為 package(含 `__init__.py`),pytest 會把 repo 根目錄加入 sys.path,故 `import agent_template` 可直接解析,無需 editable install。
- **deepagents API(已對照 0.6.12 驗證):** `create_deep_agent(model=None, tools=None, *, system_prompt=None, ...)`。prompt 參數名為 **`system_prompt`**(非 `instructions`);`model`、`tools` 為前兩個位置參數。所有對 deepagents 的呼叫集中在 `factory._build_deep_agent()` 一處。

---

### Task 1: 專案骨架與套件初始化

**Files:**
- Create: `pyproject.toml`
- Create: `agent_template/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_package.py`

**Interfaces:**
- Consumes: 無。
- Produces: 可被 import 的 `agent_template` 套件;`agent_template.__version__`(str)。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_package.py
def test_package_imports_and_has_version():
    import agent_template
    assert isinstance(agent_template.__version__, str)
    assert agent_template.__version__
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_package.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'agent_template'`

- [ ] **Step 3: 建立 pyproject 與套件**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "agent-template"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "deepagents",
    "langchain-openai",
    "langgraph",
]

[project.optional-dependencies]
dev = ["pytest"]

[tool.setuptools.packages.find]
include = ["agent_template*"]
```

```python
# agent_template/__init__.py
__version__ = "0.1.0"
```

```python
# tests/__init__.py
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_package.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml agent_template/__init__.py tests/__init__.py tests/test_package.py
git commit -m "feat(p1): scaffold agent_template package"
```

---

### Task 2: 例外型別(errors.py)

**Files:**
- Create: `agent_template/errors.py`
- Create: `tests/test_errors.py`

**Interfaces:**
- Consumes: 無。
- Produces:
  - `AgentTemplateError(Exception)` — 套件所有例外基底。
  - `ConfigError(AgentTemplateError)` — 設定不合法。
  - `ProviderError(AgentTemplateError)` — provider 建立/呼叫失敗。
  - `SecurityViolation(AgentTemplateError)` — 安全層攔截(P2/P3 使用,P1 先定義)。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_errors.py
import pytest
from agent_template.errors import (
    AgentTemplateError, ConfigError, ProviderError, SecurityViolation,
)

def test_exception_hierarchy():
    for exc in (ConfigError, ProviderError, SecurityViolation):
        assert issubclass(exc, AgentTemplateError)

def test_raise_and_catch_as_base():
    with pytest.raises(AgentTemplateError):
        raise ConfigError("bad config")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_errors.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'agent_template.errors'`

- [ ] **Step 3: 實作**

```python
# agent_template/errors.py
class AgentTemplateError(Exception):
    """agent_template 所有例外的基底。"""


class ConfigError(AgentTemplateError):
    """設定不合法。"""


class ProviderError(AgentTemplateError):
    """LLM provider 建立或呼叫失敗。"""


class SecurityViolation(AgentTemplateError):
    """安全層攔截到違規(輸入防護 / 輸出驗證 / 完整性檢查)。"""
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_errors.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent_template/errors.py tests/test_errors.py
git commit -m "feat(p1): add exception hierarchy"
```

---

### Task 3: 設定層(config.py)

**Files:**
- Create: `agent_template/config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: `agent_template.errors.ConfigError`。
- Produces:
  - `AgentConfig` frozen dataclass,欄位:
    `model: str`、`base_url: str`、`api_key: str`、
    `temperature: float = 0.0`、`max_tokens: int | None = None`、
    `timeout: float = 60.0`、`max_retries: int = 2`、`enable_audit_log: bool = True`。
  - 不合法時於 `__post_init__` raise `ConfigError`。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_config.py
import dataclasses
import pytest
from agent_template.config import AgentConfig
from agent_template.errors import ConfigError

def _valid():
    return AgentConfig(model="qwen-max", base_url="https://x/v1", api_key="k")

def test_defaults():
    c = _valid()
    assert c.temperature == 0.0
    assert c.max_tokens is None
    assert c.max_retries == 2
    assert c.enable_audit_log is True

def test_frozen():
    c = _valid()
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.model = "other"

def test_rejects_empty_model():
    with pytest.raises(ConfigError):
        AgentConfig(model="", base_url="https://x/v1", api_key="k")

def test_rejects_bad_temperature():
    with pytest.raises(ConfigError):
        AgentConfig(model="m", base_url="https://x/v1", api_key="k", temperature=-1.0)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'agent_template.config'`

- [ ] **Step 3: 實作**

```python
# agent_template/config.py
from __future__ import annotations

from dataclasses import dataclass

from .errors import ConfigError


@dataclass(frozen=True)
class AgentConfig:
    model: str
    base_url: str
    api_key: str
    temperature: float = 0.0
    max_tokens: int | None = None
    timeout: float = 60.0
    max_retries: int = 2
    enable_audit_log: bool = True

    def __post_init__(self) -> None:
        if not self.model:
            raise ConfigError("model 不可為空")
        if not self.base_url:
            raise ConfigError("base_url 不可為空")
        if not self.api_key:
            raise ConfigError("api_key 不可為空")
        if self.temperature < 0:
            raise ConfigError("temperature 不可為負")
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise ConfigError("max_tokens 須為正整數或 None")
        if self.timeout <= 0:
            raise ConfigError("timeout 須為正數")
        if self.max_retries < 0:
            raise ConfigError("max_retries 不可為負")
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent_template/config.py tests/test_config.py
git commit -m "feat(p1): add AgentConfig with validation"
```

---

### Task 4: Provider(providers.py)

**Files:**
- Create: `agent_template/providers.py`
- Create: `tests/test_providers.py`

**Interfaces:**
- Consumes: `AgentConfig`、`ProviderError`。
- Produces:
  - `build_chat_model(config)` → 回傳設定好的 `ChatOpenAI` 實例(Qwen via OpenAI 相容端點)。
  - 建立失敗時 raise `ProviderError`。

- [ ] **Step 1: 寫失敗測試**

測試以 monkeypatch 攔截 `ChatOpenAI`,驗證傳入參數正確且不需真實連線。

```python
# tests/test_providers.py
import pytest
import agent_template.providers as providers
from agent_template.config import AgentConfig
from agent_template.errors import ProviderError


class FakeChatModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_build_chat_model_passes_config(monkeypatch):
    monkeypatch.setattr(providers, "ChatOpenAI", FakeChatModel)
    cfg = AgentConfig(model="qwen-max", base_url="https://x/v1", api_key="k",
                      temperature=0.2, max_retries=3)
    model = providers.build_chat_model(cfg)
    assert model.kwargs["model"] == "qwen-max"
    assert model.kwargs["base_url"] == "https://x/v1"
    assert model.kwargs["api_key"] == "k"
    assert model.kwargs["temperature"] == 0.2
    assert model.kwargs["max_retries"] == 3


def test_build_chat_model_wraps_errors(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("init failed")
    monkeypatch.setattr(providers, "ChatOpenAI", boom)
    cfg = AgentConfig(model="m", base_url="https://x/v1", api_key="k")
    with pytest.raises(ProviderError):
        providers.build_chat_model(cfg)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_providers.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'agent_template.providers'`

- [ ] **Step 3: 實作**

```python
# agent_template/providers.py
from langchain_openai import ChatOpenAI

from .errors import ProviderError


def build_chat_model(config):
    try:
        return ChatOpenAI(
            model=config.model,
            base_url=config.base_url,
            api_key=config.api_key,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )
    except Exception as exc:
        raise ProviderError(f"建立 chat model 失敗: {exc}") from exc
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_providers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent_template/providers.py tests/test_providers.py
git commit -m "feat(p1): add Qwen chat model provider"
```

---

### Task 5: 可觀測性(observability.py)

**Files:**
- Create: `agent_template/observability.py`
- Create: `tests/test_observability.py`

**Interfaces:**
- Consumes: 無(標準函式庫 `logging`)。
- Produces:
  - `get_logger(name)` → 回傳設定好的 `logging.Logger`(輸出含名稱與層級)。
  - `audit(event)`:`event` 為 dict,寫入 audit logger(名稱 `agent_template.audit`),以 `INFO` 記錄。
  - `UsageTracker`:`record(prompt_tokens, completion_tokens)` 累加;`summary()` 回傳 dict
    `{"prompt_tokens", "completion_tokens", "total_tokens", "calls"}`。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_observability.py
import logging
from agent_template.observability import get_logger, audit, UsageTracker


def test_get_logger_returns_named_logger():
    log = get_logger("agent_template.test")
    assert isinstance(log, logging.Logger)
    assert log.name == "agent_template.test"


def test_audit_emits_record(caplog):
    with caplog.at_level(logging.INFO, logger="agent_template.audit"):
        audit({"action": "build_agent", "ok": True})
    assert any("build_agent" in r.getMessage() for r in caplog.records)


def test_usage_tracker_accumulates():
    t = UsageTracker()
    t.record(10, 5)
    t.record(3, 2)
    s = t.summary()
    assert s == {"prompt_tokens": 13, "completion_tokens": 7,
                 "total_tokens": 20, "calls": 2}
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_observability.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'agent_template.observability'`

- [ ] **Step 3: 實作**

```python
# agent_template/observability.py
import json
import logging

_AUDIT_LOGGER = "agent_template.audit"


def get_logger(name):
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def audit(event: dict):
    get_logger(_AUDIT_LOGGER).info(json.dumps(event, ensure_ascii=False, default=str))


class UsageTracker:
    def __init__(self):
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.calls = 0

    def record(self, prompt_tokens, completion_tokens):
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.calls += 1

    def summary(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "calls": self.calls,
        }
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_observability.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent_template/observability.py tests/test_observability.py
git commit -m "feat(p1): add logging, audit and usage tracking"
```

---

### Task 6: 建構入口(factory.py)

**Files:**
- Create: `agent_template/factory.py`
- Create: `tests/test_factory.py`

**Interfaces:**
- Consumes: `build_chat_model`、`AgentConfig`、`audit`、deepagents `create_deep_agent`。
- Produces:
  - `build_agent(task_prompt, tools=None, config=None)` → 回傳 deepagents agent。
  - P1 行為:`system_prompt = task_prompt`(安全外殼接縫;P2 取代為夾心組裝)。
  - `config` 為 None 時 raise `ConfigError`。
  - 成功建構時呼叫 `audit({"action": "build_agent", ...})`。

> 註:deepagents 0.6.12 的簽章為 `create_deep_agent(model=None, tools=None, *, system_prompt=None, ...)`(prompt 參數名為 `system_prompt`)。本任務把該呼叫集中在 `_build_deep_agent()` 一處,版本差異只需改這裡。測試以 monkeypatch 攔截 `factory.create_deep_agent`,不需真實 deepagents 行為。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_factory.py
import pytest
import agent_template.factory as factory
from agent_template.config import AgentConfig
from agent_template.errors import ConfigError


@pytest.fixture
def patched(monkeypatch):
    captured = {}

    def fake_build_chat_model(config):
        captured["model_built"] = True
        return "FAKE_MODEL"

    def fake_create_deep_agent(model, tools, system_prompt):
        captured["tools"] = tools
        captured["system_prompt"] = system_prompt
        captured["model"] = model
        return "FAKE_AGENT"

    monkeypatch.setattr(factory, "build_chat_model", fake_build_chat_model)
    monkeypatch.setattr(factory, "create_deep_agent", fake_create_deep_agent)
    return captured


def _cfg():
    return AgentConfig(model="qwen-max", base_url="https://x/v1", api_key="k")


def test_requires_config():
    with pytest.raises(ConfigError):
        factory.build_agent("do the task", config=None)


def test_builds_agent_with_task_prompt(patched):
    agent = factory.build_agent("do the task", tools=["t1"], config=_cfg())
    assert agent == "FAKE_AGENT"
    assert patched["system_prompt"] == "do the task"   # P1: 未包外殼
    assert patched["tools"] == ["t1"]
    assert patched["model"] == "FAKE_MODEL"


def test_tools_default_empty(patched):
    factory.build_agent("task", config=_cfg())
    assert patched["tools"] == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_factory.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'agent_template.factory'`

- [ ] **Step 3: 實作**

```python
# agent_template/factory.py
from deepagents import create_deep_agent

from .config import AgentConfig
from .errors import ConfigError
from .observability import audit
from .providers import build_chat_model


def _build_deep_agent(model, tools: list, system_prompt):
    # 隔離 deepagents 呼叫:版本差異只改這裡。
    return create_deep_agent(model=model, tools=tools, system_prompt=system_prompt)


def build_agent(task_prompt, tools: list = None, config: AgentConfig = None):
    if config is None:
        raise ConfigError("build_agent 需要 AgentConfig")
    tools = tools or []
    model = build_chat_model(config)
    # P1 接縫:安全外殼在 P2 接管,屆時改為夾心組裝。
    system_prompt = task_prompt
    agent = _build_deep_agent(model, tools, system_prompt)
    if config.enable_audit_log:
        audit({"action": "build_agent", "tools": len(tools)})
    return agent
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_factory.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent_template/factory.py tests/test_factory.py
git commit -m "feat(p1): add build_agent factory entry point"
```

---

### Task 7: 公開介面(__init__.py)與整合冒煙測試

**Files:**
- Modify: `agent_template/__init__.py`
- Create: `tests/test_public_api.py`

**Interfaces:**
- Consumes: 前述所有模組。
- Produces:`agent_template` 對外只匯出 `build_agent`、`AgentConfig`、四個例外、`__version__`。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_public_api.py
import agent_template


def test_public_surface():
    for name in ("build_agent", "AgentConfig", "AgentTemplateError",
                 "ConfigError", "ProviderError", "SecurityViolation", "__version__"):
        assert hasattr(agent_template, name), name


def test_private_modules_not_exported():
    # 私有實作不應出現在 __all__
    assert "providers" not in agent_template.__all__
    assert "factory" not in agent_template.__all__
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_public_api.py -v`
Expected: FAIL,`AttributeError` / `__all__` 不符

- [ ] **Step 3: 實作**

```python
# agent_template/__init__.py
from .config import AgentConfig
from .errors import (
    AgentTemplateError,
    ConfigError,
    ProviderError,
    SecurityViolation,
)
from .factory import build_agent

__version__ = "0.1.0"

__all__ = [
    "build_agent",
    "AgentConfig",
    "AgentTemplateError",
    "ConfigError",
    "ProviderError",
    "SecurityViolation",
    "__version__",
]
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add agent_template/__init__.py tests/test_public_api.py
git commit -m "feat(p1): expose public API surface"
```

---

## Self-Review

- **Spec coverage(P1 範圍):** 套件骨架(T1)、errors(T2)、config(T3)、provider(T4)、observability(T5)、factory 單一入口(T6)、公開介面(T7)皆有對應任務。安全外殼/編譯/RAG/CI 屬 P2–P5,刻意不在此。
- **Placeholder scan:** 無 TBD/TODO;每個 code step 均有完整程式碼與預期輸出。
- **Type consistency:** `build_agent(task_prompt, tools, config)`、`build_chat_model(config)`、`UsageTracker.record/summary`、例外名稱於各任務與 `__init__` 匯出一致。
- **接縫確認:** factory 的 `instructions = task_prompt` 與 `_build_deep_agent()` 隔離,為 P2 安全外殼預留乾淨接手點。
```
