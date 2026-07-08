# P2 — Hook / Middleware Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供 SDK 自有的 `Hook` 抽象(before/after llm、before/after tool)與內建 `session_stop` 中止機制,於建構期注入原生 DeepAgent。

**Architecture:** 遵循「SDK 自有 hook → 各框架 adapter 翻譯」的模型。開發者面對 SDK 的 `Hook` 介面(`agent_template/hooks.py`),完全不接觸 langchain。唯一知道 langchain middleware 的模組是 `agent_template/_middleware.py`(`HookMiddleware`,繼承 `langchain.agents.middleware.AgentMiddleware`),它把 SDK hooks + session_stop 翻譯成 langchain 的生命週期節點。`build_agent` 仍回傳**原生** DeepAgent 物件(執行期回歸原生)。`session_stop` 的偵測隔離在可替換的 `agent_template/session.py::is_session_stop`。

**Tech Stack:** deepagents 0.6.12、langchain.agents.middleware（`AgentMiddleware`、`hook_config`）、langchain_core.messages（`ToolMessage`、`AIMessage`）、pytest。

## Global Constraints

- **前置**：P0、P1 完成（`.venv`、`AgentConfig`/`Config`、`factory.build_agent` 皆就緒）。
- **已驗證的 langchain middleware 事實（本 phase 的地基,務必照此，勿臆測）**：
  - middleware 基底：`from langchain.agents.middleware import AgentMiddleware, hook_config`。
  - LLM 前後：override `before_model(self, state, runtime)` / `after_model(self, state, runtime)`，回傳 `dict | None`。
  - 中止一輪：方法上加 `@hook_config(can_jump_to=["end"])`，並回傳 `{"jump_to": "end"}`。**`before_model` 與 `after_model` 兩者都可如此中止（已實測）**。
  - Tool（skill/mcp）前後：override `wrap_tool_call(self, request, handler)`，回傳 `ToolMessage | Command`。呼叫 `handler(request)` 才會真正執行 tool；**不呼叫 handler 而直接回傳一個 `ToolMessage`，該 tool 就不會執行（已實測，deny/short-circuit 用）**。
  - **`wrap_tool_call` 回傳 `Command(goto=END)` 不會中止該輪（已實測會繼續）**；因此 tool 來源的 session_stop 不在 wrap_tool_call 中止，而是讓**下一個 `before_model`**(在 tool 之後、下一次 LLM 之前執行)捕捉 `state["messages"][-1]` 並中止。
  - `state` 是 dict，訊息在 `state["messages"]`。
  - `request.tool_call` 是 dict：`{"name","args","id","type"}`。
  - 完整生命週期順序（已實測）：`before_model → after_model → [wrap_tool_call: before→tool→after] → before_model → after_model → …`。
- **session_stop 偵測（MVP 約定,單點可換）**：`is_session_stop(message)` 判斷 `message.response_metadata` 或 `message.additional_kwargs`（dict）是否帶 `{"status": "session_stop"}`。團隊標準欄位敲定後**只改這一個函式**。
- **`build_agent` 仍回傳原生物件**，`hooks=None`/空清單時不掛任何我方 middleware（行為與 P1 相同）。
- **型別註記慣例**：只標註 dict/list；不 import `typing`；不標註 primitive；plain class + `__init__`（無 dataclass）。
- **執行測試**：`.venv/bin/python -m pytest`（repo 根目錄）。
- **Commit 時機**：commit 為執行期動作,由使用者決定何時執行本計畫。

---

### Task 1: SDK Hook 抽象（`hooks.py`）

**Files:**
- Create: `agent_template/hooks.py`
- Test: `tests/test_hooks.py`

**Interfaces:**
- Consumes: 無。
- Produces:
  - `StopRound(reason=None)` — sentinel;hook 方法回傳它即要求中止該輪。屬性 `.reason`。
  - `HookContext(phase, messages=None, tool_name=None, tool_args=None, result=None)` — 同名屬性。
  - `Hook` — 基底類別,方法 `before_llm(context)`、`after_llm(context)`、`before_tool(context)`、`after_tool(context)`,預設皆 `return None`。

- [ ] **Step 1: 寫測試（會失敗）**

Create `tests/test_hooks.py`:

```python
from agent_template.hooks import Hook, HookContext, StopRound


def test_stop_round_carries_reason():
    s = StopRound(reason="nope")
    assert s.reason == "nope"
    assert StopRound().reason is None


def test_hook_context_fields():
    ctx = HookContext(phase="before_tool", tool_name="ping", tool_args={"x": 1})
    assert ctx.phase == "before_tool"
    assert ctx.tool_name == "ping"
    assert ctx.tool_args == {"x": 1}
    assert ctx.messages is None
    assert ctx.result is None


def test_base_hook_methods_return_none():
    h = Hook()
    ctx = HookContext(phase="before_llm")
    assert h.before_llm(ctx) is None
    assert h.after_llm(ctx) is None
    assert h.before_tool(ctx) is None
    assert h.after_tool(ctx) is None


def test_subclass_can_return_stop_round():
    class Stopper(Hook):
        def before_tool(self, context):
            return StopRound(reason="blocked")

    result = Stopper().before_tool(HookContext(phase="before_tool"))
    assert isinstance(result, StopRound)
    assert result.reason == "blocked"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_hooks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_template.hooks'`。

- [ ] **Step 3: 實作 `hooks.py`**

Create `agent_template/hooks.py`:

```python
class StopRound:
    """由 Hook 方法回傳（或由內建 session_stop 檢查產生）以中止當前的 agent 執行（一輪）。"""

    def __init__(self, reason=None):
        self.reason = reason


class HookContext:
    """傳入 Hook 方法的生命週期資料。

    phase: "before_llm" | "after_llm" | "before_tool" | "after_tool"
    messages: 當前對話訊息（list）— llm 階段使用
    tool_name / tool_args: tool 階段使用
    result: after_llm 的 AI 訊息 / after_tool 的 tool 結果
    """

    def __init__(self, phase, messages=None, tool_name=None, tool_args=None, result=None):
        self.phase = phase
        self.messages = messages
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.result = result


class Hook:
    """開發者面對的生命週期 hook。繼承並覆寫需要的節點。
    每個方法回傳 None 表示繼續,回傳 StopRound 表示中止該輪。"""

    def before_llm(self, context):
        return None

    def after_llm(self, context):
        return None

    def before_tool(self, context):
        return None

    def after_tool(self, context):
        return None
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_hooks.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: Commit**

```bash
cd /home/xizhen/文件/temp_repo
git add agent_template/hooks.py tests/test_hooks.py
git commit -m "feat: add SDK-owned Hook abstraction (Hook, HookContext, StopRound)"
```

---

### Task 2: session_stop 偵測（`session.py`）

**Files:**
- Create: `agent_template/session.py`
- Test: `tests/test_session.py`

**Interfaces:**
- Consumes: 無（只讀訊息物件的屬性）。
- Produces:
  - `SESSION_STOP` = 字串 `"session_stop"`。
  - `is_session_stop(message)` — `message` 的 `response_metadata` 或 `additional_kwargs`（dict）帶 `{"status": "session_stop"}` 時回傳 True;`None` 或無此標記回傳 False。

- [ ] **Step 1: 寫測試（會失敗）**

Create `tests/test_session.py`:

```python
from langchain_core.messages import AIMessage, ToolMessage

from agent_template.session import is_session_stop, SESSION_STOP


def test_session_stop_constant():
    assert SESSION_STOP == "session_stop"


def test_none_is_not_session_stop():
    assert is_session_stop(None) is False


def test_ai_message_without_marker():
    assert is_session_stop(AIMessage(content="hi")) is False


def test_ai_message_response_metadata_marker():
    msg = AIMessage(content="x", response_metadata={"status": "session_stop"})
    assert is_session_stop(msg) is True


def test_tool_message_additional_kwargs_marker():
    msg = ToolMessage(content="x", tool_call_id="c1", additional_kwargs={"status": "session_stop"})
    assert is_session_stop(msg) is True


def test_tool_message_other_status_is_not_stop():
    msg = ToolMessage(content="x", tool_call_id="c1", response_metadata={"status": "ok"})
    assert is_session_stop(msg) is False
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_session.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_template.session'`。

- [ ] **Step 3: 實作 `session.py`**

Create `agent_template/session.py`:

```python
# 團隊標準化 session_stop 狀態的 MVP 約定。團隊敲定欄位/結構後,只需替換本檔。
SESSION_STOP = "session_stop"


def is_session_stop(message):
    """訊息是否帶團隊的 session_stop 狀態。

    MVP 約定（可替換）:訊息的 response_metadata 或 additional_kwargs（dict）
    帶 {"status": "session_stop"}。涵蓋 LLM 來源（AIMessage）與 tool/mcp 來源（ToolMessage）。
    """
    if message is None:
        return False
    for attr in ("response_metadata", "additional_kwargs"):
        meta = getattr(message, attr, None)
        if isinstance(meta, dict) and meta.get("status") == SESSION_STOP:
            return True
    return False
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_session.py -v`
Expected: PASS（6 passed）。

- [ ] **Step 5: Commit**

```bash
cd /home/xizhen/文件/temp_repo
git add agent_template/session.py tests/test_session.py
git commit -m "feat: add swappable is_session_stop detector"
```

---

### Task 3: 測試用假模型（`tests/fakes.py`）

**Files:**
- Create: `tests/fakes.py`
- Test: `tests/test_fakes.py`

**Interfaces:**
- Consumes: 無。
- Produces:
  - `FakeToolModel(scripted=[...])` — 支援 `bind_tools`（回傳自身）的假 chat model,依序吐出 `scripted` 內的 `AIMessage`。供後續 middleware 整合測試驅動「model→tool→model」迴圈。
  - `ping` — 一個回傳 `"pong:" + x` 的 `@tool`。

> 背景：`langchain_core` 內建的 `GenericFakeChatModel` **不支援 `bind_tools`**（會 `NotImplementedError`），無法驅動 tool 迴圈。本 fixture 是後續 Task 4/5 整合測試的前提,已實測可跑通完整 tool 迴圈。

- [ ] **Step 1: 實作 fixture**

Create `tests/fakes.py`:

```python
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.tools import tool


@tool
def ping(x: str) -> str:
    """returns pong"""
    return "pong:" + x


class FakeToolModel(BaseChatModel):
    """支援 bind_tools 的腳本化 chat model:依序吐出 scripted 內的 AIMessage。"""

    scripted: list = []
    _cursor: dict = {}

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        i = self._cursor.setdefault(id(self), 0)
        message = self.scripted[i]
        self._cursor[id(self)] = i + 1
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self):
        return "fake-tool"
```

- [ ] **Step 2: 寫 fixture smoke test（先確認能驅動完整迴圈）**

Create `tests/test_fakes.py`:

```python
from langchain_core.messages import AIMessage
from deepagents import create_deep_agent

from tests.fakes import FakeToolModel, ping


def test_fake_tool_model_drives_a_full_tool_loop():
    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "ping", "args": {"x": "hi"}, "id": "c1"}]),
        AIMessage(content="done"),
    ])
    agent = create_deep_agent(model=model, tools=[ping], system_prompt="x")
    out = agent.invoke({"messages": [("user", "go")]})
    kinds = [type(m).__name__ for m in out["messages"]]
    assert "ToolMessage" in kinds
    assert out["messages"][-1].content == "done"
```

- [ ] **Step 3: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_fakes.py -v`
Expected: PASS（1 passed）。訊息序列含 `ToolMessage`,最後一則內容為 `done`。

- [ ] **Step 4: Commit**

```bash
cd /home/xizhen/文件/temp_repo
git add tests/fakes.py tests/test_fakes.py
git commit -m "test: add FakeToolModel fixture driving a full tool loop"
```

---

### Task 4: `HookMiddleware` — LLM 路徑（before/after model + session_stop）

**Files:**
- Create: `agent_template/_middleware.py`
- Test: `tests/test_middleware.py`

**Interfaces:**
- Consumes: `agent_template.hooks`（Hook/HookContext/StopRound）、`agent_template.session`（is_session_stop、SESSION_STOP）、`langchain.agents.middleware`（AgentMiddleware、hook_config）。
- Produces: `agent_template._middleware.HookMiddleware(hooks)` — 繼承 `AgentMiddleware`;本 Task 實作 `before_model` / `after_model`。tool 路徑（`wrap_tool_call`）在 Task 5 加上。

**行為（本 Task）：**
- `before_model`：若 `state["messages"][-1]` 為 session_stop → `{"jump_to":"end"}`（捕捉 **tool/mcp 來源**的 session_stop,在下一次 LLM 前中止);否則跑所有 hook 的 `before_llm`,任一回傳 StopRound → `{"jump_to":"end"}`。
- `after_model`：若最後一則（AI 回應）為 session_stop → `{"jump_to":"end"}`（**LLM 來源**);否則跑所有 hook 的 `after_llm`,任一 StopRound → `{"jump_to":"end"}`。

- [ ] **Step 1: 寫單元 + 整合測試（會失敗）**

Create `tests/test_middleware.py`:

```python
from langchain_core.messages import AIMessage, HumanMessage
from deepagents import create_deep_agent

from agent_template._middleware import HookMiddleware
from agent_template.hooks import Hook, StopRound
from tests.fakes import FakeToolModel, ping


class _Recorder(Hook):
    def __init__(self):
        self.seen = []

    def before_llm(self, context):
        self.seen.append("before_llm")

    def after_llm(self, context):
        self.seen.append("after_llm")


def test_before_model_runs_before_llm_hooks_and_continues():
    rec = _Recorder()
    mw = HookMiddleware([rec])
    state = {"messages": [HumanMessage(content="hi")]}
    assert mw.before_model(state, None) is None
    assert rec.seen == ["before_llm"]


def test_after_model_halts_on_llm_session_stop():
    mw = HookMiddleware([])
    stop_ai = AIMessage(content="bye", response_metadata={"status": "session_stop"})
    state = {"messages": [HumanMessage(content="hi"), stop_ai]}
    assert mw.after_model(state, None) == {"jump_to": "end"}


def test_before_model_halts_when_hook_returns_stop_round():
    class Stopper(Hook):
        def before_llm(self, context):
            return StopRound()

    mw = HookMiddleware([Stopper()])
    state = {"messages": [HumanMessage(content="hi")]}
    assert mw.before_model(state, None) == {"jump_to": "end"}


def test_integration_after_model_session_stop_ends_run_before_tool():
    # LLM 首則回應即帶 session_stop → 不應呼叫 tool
    model = FakeToolModel(scripted=[
        AIMessage(content="stop", response_metadata={"status": "session_stop"},
                  tool_calls=[{"name": "ping", "args": {"x": "hi"}, "id": "c1"}]),
        AIMessage(content="should-not-reach"),
    ])
    agent = create_deep_agent(model=model, tools=[ping], system_prompt="x",
                              middleware=[HookMiddleware([])])
    out = agent.invoke({"messages": [("user", "go")]})
    contents = [getattr(m, "content", None) for m in out["messages"]]
    assert "should-not-reach" not in contents
    assert all(type(m).__name__ != "ToolMessage" for m in out["messages"])
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_middleware.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_template._middleware'`。

- [ ] **Step 3: 實作 `_middleware.py`（LLM 路徑）**

Create `agent_template/_middleware.py`:

```python
from langchain.agents.middleware import AgentMiddleware, hook_config

from .hooks import HookContext, StopRound
from .session import is_session_stop


class HookMiddleware(AgentMiddleware):
    """把 SDK Hooks + 內建 session_stop 翻譯成 langchain AgentMiddleware。
    這是唯一知道 langchain middleware 的模組;未來換框架由該框架的 adapter 另作翻譯。"""

    def __init__(self, hooks):
        super().__init__()
        self._hooks = list(hooks)

    @hook_config(can_jump_to=["end"])
    def before_model(self, state, runtime):
        messages = state["messages"]
        last = messages[-1] if messages else None
        # tool/mcp 來源的 session_stop 在此被捕捉（tool 之後、下一次 LLM 之前）
        if is_session_stop(last):
            return {"jump_to": "end"}
        context = HookContext(phase="before_llm", messages=messages)
        for hook in self._hooks:
            if isinstance(hook.before_llm(context), StopRound):
                return {"jump_to": "end"}
        return None

    @hook_config(can_jump_to=["end"])
    def after_model(self, state, runtime):
        messages = state["messages"]
        last = messages[-1] if messages else None
        # LLM 來源的 session_stop
        if is_session_stop(last):
            return {"jump_to": "end"}
        context = HookContext(phase="after_llm", messages=messages, result=last)
        for hook in self._hooks:
            if isinstance(hook.after_llm(context), StopRound):
                return {"jump_to": "end"}
        return None
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_middleware.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: Commit**

```bash
cd /home/xizhen/文件/temp_repo
git add agent_template/_middleware.py tests/test_middleware.py
git commit -m "feat: add HookMiddleware LLM-path hooks and session_stop halting"
```

---

### Task 5: `HookMiddleware.wrap_tool_call` — tool 路徑（before/after tool + StopRound short-circuit）

**Files:**
- Modify: `agent_template/_middleware.py`
- Test: `tests/test_middleware.py`（同檔追加）

**Interfaces:**
- Consumes: 追加 `from langchain_core.messages import ToolMessage`、`from .session import SESSION_STOP`。
- Produces: `HookMiddleware.wrap_tool_call(self, request, handler)`;新增私有輔助 `_stop_message(self, tool_call, content)`。

**行為：**
- 跑所有 hook 的 `before_tool`（`HookContext(phase="before_tool", tool_name, tool_args)`）。任一回傳 StopRound → **不呼叫 handler**,回傳 `_stop_message(...)`：一個帶 `response_metadata={"status": SESSION_STOP}` 的合成 `ToolMessage`。該訊息成為最後一則,下一個 `before_model` 便會中止該輪(且 tool 不執行)。
- 否則 `result = handler(request)`,跑所有 hook 的 `after_tool`（帶 `result`）。任一 StopRound → 回傳 `_stop_message(..., content=result.content)`（同樣觸發下一個 before_model 中止)。
- 否則回傳 `result`。
- tool 結果**本身**帶 session_stop（team 標準）時,不需在此處理 —— 由下一個 `before_model` 捕捉（Task 4 已實作,本 Task 加整合測試驗證)。

- [ ] **Step 1: 追加測試（會失敗）**

Append to `tests/test_middleware.py`:

```python
from langchain_core.messages import ToolMessage as _ToolMessage


class _FakeRequest:
    def __init__(self, tool_call):
        self.tool_call = tool_call


def test_wrap_tool_call_runs_tool_and_after_hook_when_allowed():
    seen = []

    class Watcher(Hook):
        def before_tool(self, context):
            seen.append(("before_tool", context.tool_name, context.tool_args))

        def after_tool(self, context):
            seen.append(("after_tool", context.result.content))

    mw = HookMiddleware([Watcher()])
    req = _FakeRequest({"name": "ping", "args": {"x": "hi"}, "id": "c1", "type": "tool_call"})
    handler_called = []

    def handler(r):
        handler_called.append(True)
        return _ToolMessage(content="pong:hi", tool_call_id="c1", name="ping")

    result = mw.wrap_tool_call(req, handler)
    assert handler_called == [True]
    assert result.content == "pong:hi"
    assert seen == [("before_tool", "ping", {"x": "hi"}), ("after_tool", "pong:hi")]


def test_before_tool_stop_round_short_circuits_tool():
    class Denier(Hook):
        def before_tool(self, context):
            return StopRound(reason="denied")

    mw = HookMiddleware([Denier()])
    req = _FakeRequest({"name": "ping", "args": {"x": "hi"}, "id": "c1", "type": "tool_call"})
    handler_called = []

    def handler(r):
        handler_called.append(True)
        return _ToolMessage(content="pong", tool_call_id="c1", name="ping")

    result = mw.wrap_tool_call(req, handler)
    assert handler_called == []  # tool did NOT run
    assert isinstance(result, _ToolMessage)
    assert result.response_metadata.get("status") == "session_stop"
    assert result.tool_call_id == "c1"


def test_integration_before_tool_deny_halts_round_and_skips_tool():
    ran = []

    class Denier(Hook):
        def before_tool(self, context):
            return StopRound()

    from tests.fakes import FakeToolModel
    from langchain_core.tools import tool

    @tool
    def rec(x: str) -> str:
        """records"""
        ran.append(x)
        return "ran"

    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "rec", "args": {"x": "hi"}, "id": "c1"}]),
        AIMessage(content="should-not-reach"),
    ])
    agent = create_deep_agent(model=model, tools=[rec], system_prompt="x",
                              middleware=[HookMiddleware([Denier()])])
    out = agent.invoke({"messages": [("user", "go")]})
    contents = [getattr(m, "content", None) for m in out["messages"]]
    assert ran == []  # tool never executed
    assert "should-not-reach" not in contents  # round halted


def test_integration_tool_result_session_stop_halts_before_next_llm():
    from tests.fakes import FakeToolModel
    from langchain_core.tools import tool

    @tool
    def stopper(x: str) -> str:
        """returns a plain value; middleware marks stop via metadata path in real mcp"""
        return "ok"

    # Simulate a tool whose ToolMessage carries session_stop by using an after_tool hook
    class MarkStop(Hook):
        def after_tool(self, context):
            return StopRound()

    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "stopper", "args": {"x": "hi"}, "id": "c1"}]),
        AIMessage(content="should-not-reach"),
    ])
    agent = create_deep_agent(model=model, tools=[stopper], system_prompt="x",
                              middleware=[HookMiddleware([MarkStop()])])
    out = agent.invoke({"messages": [("user", "go")]})
    contents = [getattr(m, "content", None) for m in out["messages"]]
    assert "should-not-reach" not in contents
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_middleware.py -v`
Expected: FAIL — `AttributeError: 'HookMiddleware' object has no attribute 'wrap_tool_call'`（或 tool 短路測試失敗）。

- [ ] **Step 3: 實作 `wrap_tool_call` 與 `_stop_message`**

Edit `agent_template/_middleware.py`：在頂端 import 區加入 `ToolMessage` 與 `SESSION_STOP`,並在 `HookMiddleware` 內新增方法：

```python
# 頂端 import 區改為：
from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain_core.messages import ToolMessage

from .hooks import HookContext, StopRound
from .session import is_session_stop, SESSION_STOP
```

在 `HookMiddleware` 類別內（`after_model` 之後）新增：

```python
    def wrap_tool_call(self, request, handler):
        tool_call = request.tool_call
        before_context = HookContext(
            phase="before_tool",
            tool_name=tool_call["name"],
            tool_args=tool_call.get("args"),
        )
        for hook in self._hooks:
            if isinstance(hook.before_tool(before_context), StopRound):
                return self._stop_message(tool_call, "stopped by hook")

        result = handler(request)

        after_context = HookContext(
            phase="after_tool",
            tool_name=tool_call["name"],
            tool_args=tool_call.get("args"),
            result=result,
        )
        for hook in self._hooks:
            if isinstance(hook.after_tool(after_context), StopRound):
                return self._stop_message(tool_call, getattr(result, "content", "stopped by hook"))

        return result

    def _stop_message(self, tool_call, content):
        # 合成一則帶 session_stop 標記的 ToolMessage;下一個 before_model 會據此中止該輪。
        return ToolMessage(
            content=content,
            tool_call_id=tool_call["id"],
            name=tool_call["name"],
            response_metadata={"status": SESSION_STOP},
        )
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_middleware.py -v`
Expected: PASS（4 + 4 = 8 passed）。

- [ ] **Step 5: Commit**

```bash
cd /home/xizhen/文件/temp_repo
git add agent_template/_middleware.py tests/test_middleware.py
git commit -m "feat: add HookMiddleware tool-path hooks with StopRound short-circuit"
```

---

### Task 6: `build_agent` 掛載 hooks

**Files:**
- Modify: `agent_template/factory.py`
- Test: `tests/test_factory.py`（同檔追加）

**Interfaces:**
- Consumes: `agent_template._middleware.HookMiddleware`。
- Produces: `build_agent(config, hooks=None)` — `hooks` 為 `Hook` 清單;非空時建 `HookMiddleware(hooks)` 並以 `middleware=[...]` 傳入 `create_deep_agent`;`None`/空清單時 `middleware=[]`（行為同 P1）。仍回傳原生物件。

- [ ] **Step 1: 追加測試（會失敗）**

Append to `tests/test_factory.py`:

```python
def test_build_agent_wires_hook_middleware_when_hooks_given(monkeypatch):
    calls = {}

    def fake_create_deep_agent(**kwargs):
        calls.update(kwargs)
        return "AGENT"

    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", fake_create_deep_agent)

    from agent_template.hooks import Hook
    cfg = AgentConfig(api_key="k", base_url="b", model="m")
    factory.build_agent(cfg, hooks=[Hook()])

    mw = calls["middleware"]
    assert len(mw) == 1
    from agent_template._middleware import HookMiddleware
    assert isinstance(mw[0], HookMiddleware)


def test_build_agent_no_hooks_passes_empty_middleware(monkeypatch):
    calls = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")

    cfg = AgentConfig(api_key="k", base_url="b", model="m")
    factory.build_agent(cfg)
    assert calls["middleware"] == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_factory.py::test_build_agent_wires_hook_middleware_when_hooks_given -v`
Expected: FAIL — `build_agent()` 目前不接受 `hooks`（TypeError）或未傳 `middleware`。

- [ ] **Step 3: 修改 `build_agent`**

Edit `agent_template/factory.py`：頂端 import 區加入 `from ._middleware import HookMiddleware`,並改寫 `build_agent`：

```python
def build_agent(config, hooks=None):
    """建構並回傳原生 DeepAgent 物件（執行期回歸原生,無包裝）。
    hooks: Hook 清單;於建構期翻譯成 middleware 注入。"""
    llm = _build_llm(config)
    middleware = [HookMiddleware(hooks)] if hooks else []
    return create_deep_agent(
        model=llm,
        tools=[],
        system_prompt=config.system_prompt,
        middleware=middleware,
    )
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_factory.py -v`
Expected: PASS（P1 的 3 項 + 本 Task 2 項 = 5 passed）。

- [ ] **Step 5: 跑全部測試確認整體綠**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS（P0 7 + P1 3 + P2:hooks 4 + session 6 + fakes 1 + middleware 8 + factory 新增 2 = 31 passed）。

- [ ] **Step 6: Commit**

```bash
cd /home/xizhen/文件/temp_repo
git add agent_template/factory.py tests/test_factory.py
git commit -m "feat: build_agent injects HookMiddleware when hooks provided"
```

---

## Self-Review

- **Spec coverage**（req.md Feature 3）：
  - 「在生命週期節點插入自定義邏輯」→ `Hook`（before/after llm、before/after tool）✅
  - 「呼叫 llm/skill/mcp 之前驗證（auth 節點）」→ `before_llm` / `before_tool`;before_tool 可 StopRound short-circuit（P4 auth 將據此實作）✅
  - 「之後若狀態為 session_stop 則停止該輪」→ 內建 session_stop:LLM 來源於 `after_model`、tool/mcp 來源於下一個 `before_model` 捕捉,均 `jump_to:end`;`is_session_stop` 隔離可換 ✅
  - 「一輪 = 一次 agent 執行」→ 中止即結束該次 invoke（不牽動 checkpointer）✅
  - 架構：SDK 自有 hook,langchain 細節僅在 `_middleware.py`;`build_agent` 仍回傳原生物件 ✅
- **Placeholder scan**：無 TBD/TODO;每步含完整、已對照實測行為的程式碼。✅
- **Type consistency**：`HookMiddleware(hooks)` 建構參數、`HookContext(phase, messages, tool_name, tool_args, result)` 欄位、`is_session_stop`/`SESSION_STOP`、`request.tool_call` dict key（name/args/id）在各 Task 與測試一致;`build_agent(config, hooks=None)` 與 P1 的 `build_agent(config)` 相容（新增具預設值的參數）。✅
- **Scope**：skill/mcp 的**實際**接入是 P3;auth 打 HTTP 是 P4;o11y 是 P5 —— 本 phase 只建 hook 骨架與 session_stop,未提前實作那些。✅
