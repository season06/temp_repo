# P1 — BaseAgent (build_agent) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 實作 `build_agent(config)`，回傳一個接上 OpenAI-compatible LLM 的**原生 DeepAgent 物件**（已可 `invoke` / `stream`）。

**Architecture:** 遵循「統一建構、執行期回歸原生」模型。`factory.py` 提供 `_build_llm`（把 `AgentConfig` 轉成 `langchain_openai.ChatOpenAI`）與 `build_agent`（呼叫 deepagents 的 `create_deep_agent`，把 model 與 system_prompt 接上，回傳原生 agent 物件）。P1 不掛任何 middleware / tools（留給 P2/P3）。

**Tech Stack:** deepagents 0.6.12（`create_deep_agent(model=..., tools=..., system_prompt=...)`）、langchain-openai 1.3.3（`ChatOpenAI`）、pytest。

## Global Constraints

- **前置**：P0 已完成（`.venv` 就緒、`deepagents==0.6.12` 與 `langchain-openai==1.3.3` 已安裝、`agent_template.config.AgentConfig` 存在）。
- **deepagents 0.6.12 API（已驗證）**：`create_deep_agent(model=None, tools=None, *, system_prompt=None, middleware=(), subagents=None, interrupt_on=None, checkpointer=None, ...)`。prompt 參數名是 **`system_prompt`**（不是 `instructions`）。
- **執行期回歸原生**：`build_agent` 回傳 deepagents 原生物件,**不做任何包裝**（無 SecureAgent）。使用者直接對回傳物件呼叫 `invoke` / `stream`。
- **測試策略**：LLM 呼叫需連線,故 P1 測試**不做實際推論**。以 monkeypatch 攔截 `ChatOpenAI` / `create_deep_agent` 驗證「參數接線正確」,再以一個不觸網的真實建構測試驗證「回傳物件具備 invoke/stream 介面」。
- **型別註記慣例**：只標註 `dict` / `list`；不 import `typing`、不標註 primitive。
- **執行測試**：`.venv/bin/python -m pytest`（repo 根目錄）。
- **Commit 時機**：commit 為執行期動作,由使用者決定何時執行本計畫。

---

### Task 1: `_build_llm` — 把 `AgentConfig` 轉為 OpenAI-compatible `ChatOpenAI`

**Files:**
- Create: `agent_template/factory.py`
- Test: `tests/test_factory.py`

**Interfaces:**
- Consumes: `agent_template.config.AgentConfig`（api_key/base_url/model/temperature）。
- Produces: `agent_template.factory._build_llm(config)` — 回傳一個 `ChatOpenAI` 實例;`build_agent` 會消費它。模組層級須有可被 monkeypatch 的名稱 `ChatOpenAI`（於 factory 頂端 `from langchain_openai import ChatOpenAI` 匯入）。

- [ ] **Step 1: 寫「參數接線」測試（會失敗）**

Create `tests/test_factory.py`:

```python
from agent_template import factory
from agent_template.config import AgentConfig


def test_build_llm_passes_openai_compatible_params(monkeypatch):
    captured = {}

    def fake_chat(**kwargs):
        captured.update(kwargs)
        return "LLM"

    monkeypatch.setattr(factory, "ChatOpenAI", fake_chat)
    cfg = AgentConfig(api_key="k", base_url="http://localhost/v1", model="qwen", temperature=0.2)
    llm = factory._build_llm(cfg)
    assert llm == "LLM"
    assert captured["api_key"] == "k"
    assert captured["base_url"] == "http://localhost/v1"
    assert captured["model"] == "qwen"
    assert captured["temperature"] == 0.2
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_factory.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_template.factory'`。

- [ ] **Step 3: 實作 `_build_llm`**

Create `agent_template/factory.py`:

```python
from langchain_openai import ChatOpenAI


def _build_llm(config):
    return ChatOpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        temperature=config.temperature,
    )
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_factory.py -v`
Expected: PASS（1 passed）。

- [ ] **Step 5: Commit**

```bash
cd /home/xizhen/文件/temp_repo
git add agent_template/factory.py tests/test_factory.py
git commit -m "feat: add _build_llm mapping AgentConfig to ChatOpenAI"
```

---

### Task 2: `build_agent` — 把 model 與 system_prompt 接上 `create_deep_agent`

**Files:**
- Modify: `agent_template/factory.py`
- Test: `tests/test_factory.py`（同檔追加）

**Interfaces:**
- Consumes: `_build_llm`、`create_deep_agent`（deepagents）。
- Produces: `agent_template.factory.build_agent(config)` — 回傳原生 deepagents agent。模組層級須有可被 monkeypatch 的名稱 `create_deep_agent`（於 factory 頂端 `from deepagents import create_deep_agent` 匯入）。

- [ ] **Step 1: 寫「接線」測試（會失敗）**

Append to `tests/test_factory.py`:

```python
def test_build_agent_wires_model_and_system_prompt(monkeypatch):
    calls = {}

    def fake_create_deep_agent(**kwargs):
        calls.update(kwargs)
        return "AGENT"

    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", fake_create_deep_agent)

    cfg = AgentConfig(api_key="k", base_url="b", model="m", system_prompt="SP")
    agent = factory.build_agent(cfg)

    assert agent == "AGENT"
    assert calls["model"] == "LLM"
    assert calls["system_prompt"] == "SP"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_factory.py::test_build_agent_wires_model_and_system_prompt -v`
Expected: FAIL — `AttributeError: module 'agent_template.factory' has no attribute 'build_agent'`。

- [ ] **Step 3: 實作 `build_agent`**

Edit `agent_template/factory.py` — 在頂端匯入區加入 `create_deep_agent`,並新增 `build_agent`：

```python
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI


def _build_llm(config):
    return ChatOpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        temperature=config.temperature,
    )


def build_agent(config):
    """建構並回傳原生 DeepAgent 物件（執行期回歸原生,無包裝）。"""
    llm = _build_llm(config)
    return create_deep_agent(
        model=llm,
        tools=[],
        system_prompt=config.system_prompt,
    )
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_factory.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: Commit**

```bash
cd /home/xizhen/文件/temp_repo
git add agent_template/factory.py tests/test_factory.py
git commit -m "feat: add build_agent wiring model and system_prompt into DeepAgent"
```

---

### Task 3: `build_agent` 回傳原生物件具備 `invoke` / `stream` 介面（不觸網真實建構）

**Files:**
- Test: `tests/test_factory.py`（同檔追加）

**Interfaces:**
- Consumes: `build_agent`（真實路徑,不 monkeypatch）。
- Produces: 無新程式碼 — 本 Task 以真實建構驗證交付契約：`build_agent(cfg)` 回傳物件同時具備可呼叫的 `invoke` 與 `stream`。

> 說明：`ChatOpenAI` 與 `create_deep_agent` 的建構皆為惰性,不會在建構期連線（只有實際 `invoke` 推論才連線）。因此本測試能真實走完 `build_agent` 而不需要可用的 LLM 端點。

- [ ] **Step 1: 寫「真實建構 + 介面存在」測試**

Append to `tests/test_factory.py`:

```python
def test_build_agent_returns_native_object_with_invoke_and_stream():
    cfg = AgentConfig(api_key="dummy", base_url="http://localhost:9/v1", model="m")
    agent = factory.build_agent(cfg)
    assert agent is not None
    assert callable(getattr(agent, "invoke", None))
    assert callable(getattr(agent, "stream", None))
```

- [ ] **Step 2: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_factory.py::test_build_agent_returns_native_object_with_invoke_and_stream -v`
Expected: PASS（1 passed）。

> 若失敗且錯誤與 `create_deep_agent` 的參數簽章有關（例如 `model` / `system_prompt` 非預期關鍵字）：以 `.venv/bin/python -c "import inspect, deepagents; print(inspect.signature(deepagents.create_deep_agent))"` 核對實際簽章,修正 `build_agent` 的關鍵字後重跑。不要改動測試對「回傳物件須有 invoke/stream」的斷言。

- [ ] **Step 3: 跑全部測試確認整體綠**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS（P0 的 7 項 + P1 的 3 項 = 10 passed）。

- [ ] **Step 4: Commit**

```bash
cd /home/xizhen/文件/temp_repo
git add tests/test_factory.py
git commit -m "test: verify build_agent returns native object exposing invoke/stream"
```

---

## Self-Review

- **Spec coverage**：對應 req.md Feature 1（BaseAgent）與「架構模型」。`build_agent` 回傳原生物件（統一建構、執行期回歸原生）✅；LLM 走 OpenAI-compatible（`ChatOpenAI` + base_url/api_key/model）✅；`AgentConfig` 的 temperature/system_prompt 接線 ✅。tools/middleware 留待 P2/P3（本 phase 明確不做）。
- **Placeholder scan**：無 TBD/TODO;所有步驟皆含完整程式碼與明確預期輸出。Task 3 的 fallback 診斷指令為真實可執行指令,非佔位。✅
- **Type consistency**：`_build_llm(config)` → `ChatOpenAI`,`build_agent(config)` 消費 `_build_llm` 回傳值並傳給 `create_deep_agent(model=..., system_prompt=...)`;monkeypatch 目標名稱（`factory.ChatOpenAI`、`factory.create_deep_agent`）與 factory 頂端匯入名稱一致。`AgentConfig` 屬性名與 P0 定義一致。✅
