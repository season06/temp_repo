# Mandatory Auth Hook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make身分認證成為 SDK 強制、不可移除的機制 —— 每次 agent 呼叫前先在入口驗證呼叫端身分,per-tool auth 也自動注入。

**Architecture:** 抽出單一 middleware 組裝咽喉點 `assemble_middleware`,它永遠把 `AuthMiddleware`(入口)放最前、並在 `HookMiddleware` 內把 `AuthHook`(per-tool)排在使用者 hook 之前。所有 provider builder 都只經由此 helper,故「無 auth 的 middleware 清單」不存在。入口驗不過 `raise AuthenticationError`;per-tool 維持 `StopRound`。身分由呼叫端在 `invoke`/`ainvoke` 時以 `context=` 傳入,middleware 從 `runtime.context` 讀取。

**Tech Stack:** Python 3.14、langchain 1.3.11(`AgentMiddleware.before_agent`)、deepagents 0.6.12(`create_deep_agent(context_schema=...)`)、httpx、pydantic v2、pytest。

## Global Constraints

- 設計來源:`docs/superpowers/specs/2026-07-11-mandatory-auth-hook-design.md`(Approach B)。
- 強制程度只做「API 設計強制(擋意外)」;不做編譯硬化。
- 入口拒絕 = `raise AuthenticationError`;per-tool 拒絕 = `StopRound`(不變)。
- 身分來源 = `runtime.context`(呼叫端 `context={"identity": ...}` 或 `AuthContext(identity=...)`)。
- Fail-closed:`config.auth.endpoint` 未設 → build 期 `raise ValueError`;端點錯誤/非 200 → deny;缺 identity → deny(不打網路)。
- 型別註記沿用本檔既有風格(`from __future__ import annotations`、`Any`、`X | None`、`dict`/`list`)。
- 測試指令:`.venv/bin/python -m pytest`(repo 根目錄)。
- 每次 commit 訊息結尾加:`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。
- 已驗證事實(不需再 spike):`before_agent` 於 `invoke` 與 `ainvoke` 皆會觸發,其中 `raise` 會乾淨傳播出 invoke;`create_deep_agent` 收 `context_schema`;`context=` dict 會被 coerce 成 `context_schema` dataclass,`getattr(runtime.context, "identity", None)` 可讀出。

---

### Task 1: 身分 payload + AuthContext + AuthenticationError

**Files:**
- Modify: `agent_template/hooks/base.py`（新增 `AuthenticationError`）
- Modify: `agent_template/auth/clients.py`（新增 `AuthContext`、`_auth_payload`;改 `HttpAuthClient.verify`）
- Test: `tests/test_auth.py`（追加）

**Interfaces:**
- Produces:
  - `agent_template.hooks.base.AuthenticationError(Exception)`
  - `agent_template.auth.clients.AuthContext`（dataclass,欄位 `identity: str | None = None`）
  - `agent_template.auth.clients._auth_payload(context) -> dict`（只放存在的 `tool` / `identity`）
  - `HttpAuthClient.verify(context) -> bool`（payload 改由 `_auth_payload` 產生）

- [ ] **Step 1: 為 payload helper 寫失敗測試**

在 `tests/test_auth.py` 末尾追加：

```python
def test_auth_payload_picks_tool_only():
    from agent_template.auth.clients import _auth_payload
    from agent_template.hooks import HookContext
    assert _auth_payload(HookContext(phase="before_tool", tool_name="t")) == {"tool": "t"}


def test_auth_payload_picks_identity_only():
    from agent_template.auth.clients import _auth_payload, AuthContext
    assert _auth_payload(AuthContext(identity="u1")) == {"identity": "u1"}


def test_auth_payload_empty_when_no_fields():
    from agent_template.auth.clients import _auth_payload, AuthContext
    assert _auth_payload(AuthContext()) == {}


def test_http_auth_client_sends_identity(monkeypatch):
    from agent_template.auth.clients import AuthContext
    captured = {}

    def capture(url, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse(200)

    monkeypatch.setattr(auth_mod.httpx, "post", capture)
    HttpAuthClient("http://auth/verify").verify(AuthContext(identity="alice"))
    assert captured["json"] == {"identity": "alice"}
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_auth.py -k "auth_payload or sends_identity" -v`
Expected: FAIL(`ImportError: cannot import name '_auth_payload'` / `AuthContext`）

- [ ] **Step 3: 實作 AuthenticationError**

在 `agent_template/hooks/base.py` 檔尾追加：

```python
class AuthenticationError(Exception):
    """入口身分認證未通過時由 AuthMiddleware 拋出;呼叫端可據此與一般錯誤區分。"""
```

- [ ] **Step 4: 實作 AuthContext 與 _auth_payload,改寫 HttpAuthClient.verify**

在 `agent_template/auth/clients.py`:

頂部 import 區加入（`from __future__ import annotations` 之後）：

```python
from dataclasses import dataclass
```

在 `AuthClient` 類別**之前**加入：

```python
@dataclass
class AuthContext:
    """呼叫端在 invoke/ainvoke 時透過 context= 傳入的身分;middleware 由 runtime.context 讀取。"""

    identity: str | None = None


def _auth_payload(context: Any) -> dict:
    """組出要送給 auth 端點的欄位(只放存在的)。
    per-tool 來的 HookContext 帶 tool_name;入口來的 AuthContext 帶 identity。"""
    payload: dict = {}
    tool = getattr(context, "tool_name", None)
    if tool is not None:
        payload["tool"] = tool
    identity = getattr(context, "identity", None)
    if identity is not None:
        payload["identity"] = identity
    return payload
```

把 `HttpAuthClient.verify` 的 `httpx.post` 那行改成用 `_auth_payload`：

```python
    def verify(self, context: Any) -> bool:
        try:
            response = httpx.post(self._endpoint, json=_auth_payload(context), timeout=self._timeout)
        except Exception:
            return False
        return response.status_code == 200
```

- [ ] **Step 5: 跑測試確認通過(含既有 tool payload 測試不回歸)**

Run: `.venv/bin/python -m pytest tests/test_auth.py -v`
Expected: PASS(含既有 `test_http_auth_client_sends_tool_name` 仍綠 —— HookContext 無 identity,payload 仍是 `{"tool": "mytool"}`）

- [ ] **Step 6: Commit**

```bash
git add agent_template/hooks/base.py agent_template/auth/clients.py tests/test_auth.py
git commit -m "feat(auth): add AuthContext, identity payload helper, AuthenticationError

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: AuthMiddleware(入口強制認證)

**Files:**
- Modify: `agent_template/hooks/middleware.py`（新增 `AuthMiddleware`）
- Modify: `agent_template/hooks/__init__.py`（export `AuthMiddleware`、`AuthenticationError`）
- Test: `tests/test_auth_middleware.py`（新增）

**Interfaces:**
- Consumes:`AuthenticationError`（Task 1）、任何具 `.verify(context) -> bool` 的 client（如 `HttpAuthClient`,Task 1）。
- Produces:`agent_template.hooks.AuthMiddleware(client)` —— langchain `AgentMiddleware`,實作 `before_agent`;缺 identity 或 verify 失敗即 `raise AuthenticationError`,不改狀態時回 `None`。

- [ ] **Step 1: 寫失敗測試**

新建 `tests/test_auth_middleware.py`：

```python
import asyncio

import pytest
from langchain_core.messages import AIMessage
from deepagents import create_deep_agent

from agent_template.hooks import AuthMiddleware, AuthenticationError
from agent_template.auth.clients import AuthContext
from tests.fakes import FakeToolModel


class _Allow:
    def __init__(self):
        self.calls = 0

    def verify(self, context):
        self.calls += 1
        return True


class _Deny:
    def verify(self, context):
        return False


class _RT:
    def __init__(self, context):
        self.context = context


def test_auth_middleware_allows_when_identity_and_client_ok():
    mw = AuthMiddleware(_Allow())
    assert mw.before_agent({}, _RT(AuthContext(identity="u1"))) is None


def test_auth_middleware_denies_raises():
    mw = AuthMiddleware(_Deny())
    with pytest.raises(AuthenticationError):
        mw.before_agent({}, _RT(AuthContext(identity="u1")))


def test_auth_middleware_missing_identity_raises_without_calling_client():
    client = _Allow()
    mw = AuthMiddleware(client)
    with pytest.raises(AuthenticationError):
        mw.before_agent({}, _RT(AuthContext()))          # identity=None
    assert client.calls == 0                              # 未打網路,純 fail-closed


def test_auth_middleware_none_context_raises():
    mw = AuthMiddleware(_Allow())
    with pytest.raises(AuthenticationError):
        mw.before_agent({}, _RT(None))


def _agent(client):
    return create_deep_agent(
        model=FakeToolModel(scripted=[AIMessage(content="ok")]),
        tools=[], system_prompt="x",
        middleware=[AuthMiddleware(client)],
    )


def test_entry_auth_denies_invoke_end_to_end():
    with pytest.raises(AuthenticationError):
        _agent(_Deny()).invoke({"messages": [("user", "hi")]}, context={"identity": "u1"})


def test_entry_auth_allows_invoke_end_to_end():
    out = _agent(_Allow()).invoke({"messages": [("user", "hi")]}, context={"identity": "u1"})
    assert out["messages"][-1].content == "ok"


def test_entry_auth_denies_ainvoke_end_to_end():
    with pytest.raises(AuthenticationError):
        asyncio.run(_agent(_Deny()).ainvoke({"messages": [("user", "hi")]}, context={"identity": "u1"}))
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_auth_middleware.py -v`
Expected: FAIL(`ImportError: cannot import name 'AuthMiddleware'`）

- [ ] **Step 3: 實作 AuthMiddleware**

在 `agent_template/hooks/middleware.py`:

更新 import（`from .base import ...` 那行）加入 `AuthenticationError`：

```python
from .base import Hook, HookContext, StopRound, AuthenticationError
```

在 `HookMiddleware` 類別**之前**新增：

```python
class AuthMiddleware(AgentMiddleware):
    """SDK 強制的入口身分認證。每次 agent 執行前(before_agent)驗證呼叫端身分;
    未通過直接 raise AuthenticationError,LLM/tools 完全不會執行。
    由 assemble_middleware 注入且排在最前,使用者無法移除或繞過。

    僅實作 before_agent(sync);ainvoke 亦回退呼叫本方法。
    MVP 限制:sync client 於 async 執行下會短暫阻塞 event loop(與 AuthHook 相同,已文件化)。"""

    def __init__(self, client: Any) -> None:
        super().__init__()
        self._client = client

    def before_agent(self, state: dict, runtime: Any) -> dict | None:
        context = getattr(runtime, "context", None)
        identity = getattr(context, "identity", None)
        if identity is None or not self._client.verify(context):
            raise AuthenticationError("authentication required before agent invocation")
        return None
```

- [ ] **Step 4: export**

在 `agent_template/hooks/__init__.py` 更新：

```python
from .base import Hook, HookContext, StopRound, AuthenticationError
from .middleware import HookMiddleware, AuthMiddleware
from .session import SESSION_STOP, is_session_stop, make_session_stop_metadata
```

- [ ] **Step 5: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_auth_middleware.py -v`
Expected: PASS(7 案全綠）

- [ ] **Step 6: Commit**

```bash
git add agent_template/hooks/middleware.py agent_template/hooks/__init__.py tests/test_auth_middleware.py
git commit -m "feat(auth): add AuthMiddleware entry gate that raises on failed auth

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: assemble_middleware 咽喉點 + build_deepagent 接線

**Files:**
- Modify: `agent_template/core/factory.py`（新增 `assemble_middleware`;`build_deepagent` 改用它 + `context_schema`）
- Modify: `agent_template/auth/__init__.py`（export `AuthContext`、re-export `AuthenticationError`）
- Test: `tests/test_factory.py`（追加新測試;既有 `_cfg` 與 2 個 middleware 測試在 Task 4 更新)

**Interfaces:**
- Consumes:`AuthMiddleware`（Task 2）、`HttpAuthClient`/`AuthHook`/`AuthContext`（Task 1 + 既有）、`HookMiddleware`/`ObservabilityMiddleware`（既有）。
- Produces:`factory.assemble_middleware(config, hooks=None, observability=None) -> list` —— 永遠 `[AuthMiddleware, HookMiddleware([AuthHook, *hooks]), *observability]`;`config.auth.endpoint` 未設則 `raise ValueError`。`build_deepagent` 傳 `context_schema=AuthContext` 給 `create_deep_agent`。

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_factory.py` 末尾追加（`AuthConfig` 需 import,見下方 Step 也會在 Task 4 加到 `_cfg`;此處測試自帶 endpoint）：

```python
def _cfg_auth(endpoint="http://auth/verify"):
    from agent_template.config import AuthConfig
    cfg = _cfg(api_key="k", base_url="b", model="m")
    cfg.auth = AuthConfig(endpoint=endpoint)
    return cfg


def test_assemble_middleware_auth_first_then_hookmiddleware():
    from agent_template.hooks import AuthMiddleware, HookMiddleware
    mw = factory.assemble_middleware(_cfg_auth())
    assert isinstance(mw[0], AuthMiddleware)
    assert isinstance(mw[1], HookMiddleware)
    assert len(mw) == 2


def test_assemble_middleware_injects_authhook_before_user_hooks():
    from agent_template.auth import AuthHook
    from agent_template.hooks import Hook
    user = Hook()
    mw = factory.assemble_middleware(_cfg_auth(), hooks=[user])
    hookmw_hooks = mw[1]._hooks
    assert isinstance(hookmw_hooks[0], AuthHook)   # auth 先
    assert hookmw_hooks[1] is user                 # 使用者 hook 疊加在後


def test_assemble_middleware_missing_endpoint_raises():
    import pytest
    cfg = _cfg(api_key="k", base_url="b", model="m")   # 無 auth endpoint
    with pytest.raises(ValueError, match="auth endpoint not configured"):
        factory.assemble_middleware(cfg)


def test_build_missing_auth_endpoint_raises(monkeypatch):
    import pytest
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: "AGENT")
    cfg = _cfg(api_key="k", base_url="b", model="m")   # 無 auth endpoint
    with pytest.raises(ValueError, match="auth endpoint not configured"):
        factory.get_provider_builder(cfg)


def test_build_passes_context_schema(monkeypatch):
    from agent_template.auth import AuthContext
    calls = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")
    factory.get_provider_builder(_cfg_auth())
    assert calls["context_schema"] is AuthContext
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_factory.py -k "assemble or missing_auth or context_schema" -v`
Expected: FAIL(`AttributeError: module 'factory' has no attribute 'assemble_middleware'`）

- [ ] **Step 3: 實作 assemble_middleware 並接進 build_deepagent**

在 `agent_template/core/factory.py`:

更新 import 區：

```python
from ..hooks import HookMiddleware, AuthMiddleware
from ..observability import ObservabilityMiddleware
from ..auth import HttpAuthClient, AuthHook, AuthContext
```

（`if TYPE_CHECKING` 區的 `from ..config import Config, LLMConfig` 保留。）

在 `build_deepagent` **之前**新增：

```python
def assemble_middleware(config: Config, hooks: list | None = None, observability: Any = None) -> list:
    """唯一的 middleware 組裝點:auth 永遠最前且不可移除。
    所有 provider builder 都經此組 middleware,故「無 auth 的 middleware 清單」在結構上不存在。
    config.auth.endpoint 未設 → fail-closed,直接拒絕 build。"""
    if not config.auth.endpoint:
        raise ValueError(
            "auth endpoint not configured; mandatory authentication requires config.auth.endpoint (AUTH_ENDPOINT)"
        )
    auth_client = HttpAuthClient(config.auth.endpoint)
    middleware: list = [
        AuthMiddleware(auth_client),
        HookMiddleware([AuthHook(auth_client), *(hooks or [])]),
    ]
    if observability is not None and observability.enabled:
        middleware.append(ObservabilityMiddleware(observability.instruments, observability.logger, config.llm.model))
    return middleware
```

把 `build_deepagent` 改成：

```python
def build_deepagent(config: Config, hooks: list | None = None, tools: list | None = None, observability: Any = None) -> Any:
    """deepagent provider:由 config.llm 建 ChatOpenAI,經 assemble_middleware 組入強制 auth,回傳原生 DeepAgent 物件。"""
    llm = _build_llm(config.llm)
    middleware = assemble_middleware(config, hooks, observability)
    return create_deep_agent(
        model=llm,
        tools=tools or [],
        system_prompt=config.agent.system_prompt,
        middleware=middleware,
        context_schema=AuthContext,
    )
```

- [ ] **Step 4: export AuthContext / AuthenticationError**

`agent_template/auth/__init__.py` 改成：

```python
from .clients import AuthClient, HttpAuthClient, AuthHook, AsyncAuthClient, AsyncHttpAuthClient, AuthContext
from ..hooks import AuthenticationError
```

- [ ] **Step 5: 跑新測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_factory.py -k "assemble or missing_auth or context_schema" -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add agent_template/core/factory.py agent_template/auth/__init__.py tests/test_factory.py
git commit -m "feat(auth): route all providers through assemble_middleware with mandatory auth

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: 對齊既有測試(auth 現為強制)

強制 auth 讓「經 factory build 但未設 auth endpoint」的既有測試會失敗。此 task 只更新測試/共用 helper,不改 production。

**Files:**
- Modify: `tests/test_factory.py`（`_cfg` 加 auth endpoint;改寫 2 個 middleware 斷言測試)
- Modify: `tests/test_builder.py`（`_cfg` 加 auth endpoint）
- Modify: `tests/test_acceptance.py`（`_cfg` 加 auth endpoint;2 個經 factory 的測試補 allow client + context)

- [ ] **Step 1: 先跑全測,確認哪些紅**

Run: `.venv/bin/python -m pytest -q`
Expected: 多個 FAIL(`ValueError: auth endpoint not configured` 於 test_factory/test_builder/test_acceptance 經 factory build 的案例)

- [ ] **Step 2: test_factory.py —— `_cfg` 帶 auth endpoint**

把 `tests/test_factory.py` 的 `_cfg` 改成：

```python
def _cfg(system_prompt=None, **llm):
    from agent_template.config import AuthConfig
    return Config(llm=LLMConfig(**llm), agent=AgentSettings(system_prompt=system_prompt),
                  auth=AuthConfig(endpoint="http://auth/verify"))
```

（如此 `_cfg_auth` 可簡化為直接呼叫 `_cfg`,但保留不影響。）

- [ ] **Step 3: test_factory.py —— 改寫 2 個 middleware 斷言測試**

`test_build_agent_no_hooks_passes_empty_middleware` 改為（現在永遠有 AuthMiddleware + HookMiddleware）：

```python
def test_build_agent_no_hooks_still_has_auth_and_hook_middleware(monkeypatch):
    calls = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")
    factory.get_provider_builder(_cfg(api_key="k", base_url="b", model="m"))
    from agent_template.hooks import AuthMiddleware, HookMiddleware
    mw = calls["middleware"]
    assert isinstance(mw[0], AuthMiddleware)
    assert isinstance(mw[1], HookMiddleware)
    assert len(mw) == 2
```

`test_build_agent_wires_hook_middleware_when_hooks_given` 改為：

```python
def test_build_agent_wires_hook_middleware_when_hooks_given(monkeypatch):
    calls = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")

    from agent_template.hooks import Hook, AuthMiddleware, HookMiddleware
    from agent_template.auth import AuthHook
    user = Hook()
    factory.get_provider_builder(_cfg(api_key="k", base_url="b", model="m"), hooks=[user])

    mw = calls["middleware"]
    assert isinstance(mw[0], AuthMiddleware)
    assert isinstance(mw[1], HookMiddleware)
    assert isinstance(mw[1]._hooks[0], AuthHook)   # auth 先
    assert mw[1]._hooks[1] is user                 # 使用者 hook 在後
```

- [ ] **Step 3b: test_factory.py —— 修正 Task 3 的兩個「缺 endpoint」測試**

`_cfg` 現在永遠帶 endpoint,但 Task 3 新增的 `test_assemble_middleware_missing_endpoint_raises` 與 `test_build_missing_auth_endpoint_raises` 靠「`_cfg` 無 endpoint」來證明 fail-closed。改成明確把 auth 覆寫回無 endpoint:

`test_assemble_middleware_missing_endpoint_raises` 改為:

```python
def test_assemble_middleware_missing_endpoint_raises():
    import pytest
    from agent_template.config import AuthConfig
    cfg = _cfg(api_key="k", base_url="b", model="m")
    cfg.auth = AuthConfig()   # 無 endpoint → fail-closed
    with pytest.raises(ValueError, match="auth endpoint not configured"):
        factory.assemble_middleware(cfg)
```

`test_build_missing_auth_endpoint_raises` 改為:

```python
def test_build_missing_auth_endpoint_raises(monkeypatch):
    import pytest
    from agent_template.config import AuthConfig
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: "AGENT")
    cfg = _cfg(api_key="k", base_url="b", model="m")
    cfg.auth = AuthConfig()   # 無 endpoint
    with pytest.raises(ValueError, match="auth endpoint not configured"):
        factory.get_provider_builder(cfg)
```

（若 Task 3 定義的 `_cfg_auth` helper 因 `_cfg` 現已自帶 endpoint 而變冗餘,可保留不動 —— 它重設 auth 無害。）

- [ ] **Step 4: test_builder.py —— `_cfg` 帶 auth endpoint**

把 `tests/test_builder.py` 的 `_cfg` 改成（import 已含所需項;加 `AuthConfig`)：

```python
from agent_template.config import Config, LLMConfig, AgentSettings, SkillsConfig, McpsConfig, LocalSkill, LocalMcp, AuthConfig


def _cfg(skills=None, mcps=None):
    return Config(
        llm=LLMConfig(api_key="k", base_url="b", model="m"),
        agent=AgentSettings(system_prompt="x"),
        skills=SkillsConfig(local=skills or []),
        mcps=McpsConfig(local=mcps or []),
        auth=AuthConfig(endpoint="http://auth/verify"),
    )
```

- [ ] **Step 5: test_acceptance.py —— `_cfg` 帶 endpoint + 2 個經 factory 測試補 allow/context**

`_cfg` 改為：

```python
def _cfg():
    from agent_template.config import AuthConfig
    return Config(llm=LLMConfig(api_key="k", base_url="http://x/v1", model="m"),
                  agent=AgentSettings(system_prompt="x"),
                  auth=AuthConfig(endpoint="http://auth/verify"))
```

`test_acceptance_build_invoke_and_stream` 改為(補 allow client + `context=`)：

```python
def test_acceptance_build_invoke_and_stream(monkeypatch):
    monkeypatch.setattr(factory, "HttpAuthClient", lambda ep: _Allow())   # 入口 auth 放行
    ctx = {"identity": "acceptance"}

    model = FakeToolModel(scripted=[AIMessage(content="hello-response")])
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: model)
    agent = AgentBuilder(_cfg()).build()
    out = agent.invoke({"messages": [("user", "hi")]}, context=ctx)
    assert out["messages"][-1].content == "hello-response"

    stream_model = FakeToolModel(scripted=[AIMessage(content="streamed")])
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: stream_model)
    stream_agent = AgentBuilder(_cfg()).build()
    chunks = list(stream_agent.stream({"messages": [("user", "hi")]}, context=ctx))
    assert len(chunks) > 0
```

`test_acceptance_mcp_and_skill_tools_are_called` 於 build 前補 monkeypatch,並在 `ainvoke` 補 `context=`：

```python
def test_acceptance_mcp_and_skill_tools_are_called(monkeypatch):
    monkeypatch.setattr(factory, "HttpAuthClient", lambda ep: _Allow())   # 入口 auth 放行
    server = os.path.join(os.path.dirname(__file__), "mcp_server.py")
    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "echo", "args": {"text": "x"}, "id": "c1"}]),
        AIMessage(content="", tool_calls=[{"name": "greet", "args": {}, "id": "c2"}]),
        AIMessage(content="done"),
    ])
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: model)
    agent = (AgentBuilder(_cfg())
             .add_mcp("t", "stdio", server)
             .add_skill("greet", SKILL_FIXTURE)
             .build())
    out = asyncio.run(agent.ainvoke({"messages": [("user", "go")]}, context={"identity": "acceptance"}))
    contents = [str(getattr(m, "content", None)) for m in out["messages"]]
    assert any("echo:x" in c for c in contents)
    assert any("hi-from-skill" in c for c in contents)
```

（其餘 acceptance 測試直接用 `create_deep_agent`,不經 factory,無需改動。）

- [ ] **Step 6: 跑全測試,確認只剩 test_example_agent.py 兩案紅**

Run: `.venv/bin/python -m pytest -q`
Expected: 僅 `tests/test_example_agent.py` 的 2 案仍紅(`test_build_example_agent_runs_skill_tool`、`test_build_example_agent_default_auth_from_config_builds`)—— 它們依賴 Task 5 移除的 `auth_client=` 參數與新的 context 身分,故留待 Task 5 隨 `examples/agent.py` 一併更新。其餘全數 PASS(原有 + Task 1–3 新增)。若有其它檔案仍紅,停下回報。

- [ ] **Step 7: Commit**

```bash
git add tests/test_factory.py tests/test_builder.py tests/test_acceptance.py
git commit -m "test: align existing suites with mandatory auth (endpoint + entry allow/context)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: 範例、文件、端到端煙霧

**Files:**
- Modify: `agent_template/core/__init__.py`（export `assemble_middleware`,可選)
- Modify: `examples/agent.py`（移除手動 `AuthHook`,`__main__` 補 `context=`）
- Modify: `tests/test_example_agent.py`（對齊新簽章 + 強制 auth:移除 `auth_client=`、補 endpoint/allow/context)
- Modify: `README.md`（auth 章節:改述強制入口 auth + context 用法)
- Modify: `docs/superpowers/specs/2026-07-11-mandatory-auth-hook-design.md`（把「待驗證」標為已驗證)

**Interfaces:**
- Consumes:Task 1–3 的成品。

- [ ] **Step 1: export assemble_middleware(可選,便於自訂 provider adapter 重用)**

`agent_template/core/__init__.py` 改為：

```python
from .factory import build_deepagent, register_provider, get_provider_builder, assemble_middleware
from .builder import AgentBuilder
```

- [ ] **Step 2: 更新 examples/agent.py**

因 `AuthHook` 現由 `assemble_middleware` 自動注入,範例不再手動加,否則 per-tool auth 會重複。改為：

```python
"""示範 Agent:用 agent_template 串起(強制)auth / MCP / skill / observability / hooks。"""

from agent_template.core import AgentBuilder


def build_example_agent(config, observability=None, extra_hooks=None):
    """組出一個示範 agent 並回傳原生物件。

    auth 由 SDK 於 build 時強制注入(入口 + per-tool),使用者無法移除;
    只需在 config.auth.endpoint 設好端點即可。呼叫時以 context={"identity": ...} 傳入身分。
    extra_hooks: 額外的商業邏輯 Hook,會疊加在強制 auth 之後執行。
    """
    builder = AgentBuilder(config, observability=observability)
    for hook in (extra_hooks or []):
        builder.add_hook(hook)
    return builder.build()


if __name__ == "__main__":
    import asyncio

    from agent_template.config import Config
    from agent_template.observability import setup_observability

    config = Config.load("config.yaml", ".env")   # .env 需含 AUTH_ENDPOINT
    agent = build_example_agent(config, observability=setup_observability(config.observability))
    result = asyncio.run(agent.ainvoke(
        {"messages": [("user", "Hello!")]},
        context={"identity": "demo-user"},
    ))
    print(result["messages"][-1].content)
```

- [ ] **Step 2b: 更新 tests/test_example_agent.py(對齊新簽章 + 強制 auth)**

`build_example_agent` 已無 `auth_client=` 參數,auth 改由 config.auth.endpoint 於 build 時強制注入;兩案都需:設 auth endpoint、monkeypatch `factory.HttpAuthClient` 放行、`ainvoke` 補 `context={"identity": ...}`。改為：

```python
import asyncio
import os

from langchain_core.messages import AIMessage

import agent_template.core.factory as factory
from agent_template.config import Config, LLMConfig, AgentSettings, SkillsConfig, AuthConfig, LocalSkill
from examples.agent import build_example_agent
from tests.fakes import FakeToolModel

SKILL_FIXTURE = os.path.join(os.path.dirname(__file__), "skill_fixture.py")


class _Allow:
    def verify(self, context):
        return True


def _cfg(**over):
    base = dict(llm=LLMConfig(api_key="k", base_url="http://x/v1", model="m"),
                agent=AgentSettings(system_prompt="x"),
                auth=AuthConfig(endpoint="http://auth/verify"))
    base.update(over)
    return Config(**base)


def test_build_example_agent_runs_skill_tool(monkeypatch):
    monkeypatch.setattr(factory, "HttpAuthClient", lambda ep: _Allow())   # 入口 auth 放行
    cfg = _cfg(skills=SkillsConfig(local=[LocalSkill(name="greet", path=SKILL_FIXTURE)]))
    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "greet", "args": {}, "id": "c1"}]),
        AIMessage(content="done"),
    ])
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: model)
    agent = build_example_agent(cfg)
    out = asyncio.run(agent.ainvoke({"messages": [("user", "hello")]}, context={"identity": "demo"}))
    contents = [str(getattr(m, "content", None)) for m in out["messages"]]
    assert any("hi-from-skill" in c for c in contents)  # skill tool (from config) executed
    assert out["messages"][-1].content == "done"


def test_build_example_agent_default_auth_from_config_builds(monkeypatch):
    monkeypatch.setattr(factory, "HttpAuthClient", lambda ep: _Allow())   # 入口 auth 放行
    cfg = _cfg()
    model = FakeToolModel(scripted=[AIMessage(content="ok")])
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: model)
    agent = build_example_agent(cfg)
    assert agent is not None
    out = asyncio.run(agent.ainvoke({"messages": [("user", "hi")]}, context={"identity": "demo"}))
    assert out["messages"][-1].content == "ok"
```

- [ ] **Step 3: 更新 README auth 章節**

在 `README.md` 找到描述 auth / AuthHook 的段落,改述為：

```markdown
## 身分認證(強制)

每次呼叫 agent 前,SDK 會在入口強制執行身分認證,且 per-tool 層也會自動驗證 —— 這是不可移除、
不可繞過的機制(於 build 時由 `assemble_middleware` 注入,auth 永遠排在最前)。

- 設定端點:`.env` 的 `AUTH_ENDPOINT`(未設則 build 直接失敗,fail-closed)。
- 傳入身分:呼叫時用 `context=`,例如
  `agent.invoke({"messages": [...]}, context={"identity": "alice"})`。
- 驗不過:入口 `raise AuthenticationError`;per-tool `StopRound` 中止該輪。
- 疊加自有 hook:`builder.add_hook(MyHook())` 仍可用,會排在強制 auth 之後執行。
```

- [ ] **Step 4: spec 收尾 —— 把「待驗證」標為已驗證**

在 `docs/superpowers/specs/2026-07-11-mandatory-auth-hook-design.md` 的「待驗證」段落改為「已驗證(實作期確認)」,並註明:`before_agent` 於 `invoke`/`ainvoke` 皆觸發且 raise 乾淨傳播;`context=` dict 會 coerce 成 `AuthContext` 並可由 `runtime.context` 讀出;入口採 sync `before_agent`(async 下短暫阻塞,MVP 接受,與 AuthHook 一致)。

- [ ] **Step 5: 端到端煙霧驗證**

新建暫存腳本並執行(驗證強制性:未給 context 會被擋、給了 context 且端點放行才過)。用一個本機 stub auth 端點以 monkeypatch 方式在測試中已覆蓋;此處以既有測試為煙霧來源:

Run: `.venv/bin/python -m pytest tests/test_auth_middleware.py tests/test_factory.py tests/test_acceptance.py -q`
Expected: 全數 PASS —— 證明入口 deny→raise、allow+context→通過、缺 endpoint→build 失敗、缺 identity→raise。

- [ ] **Step 6: 全測試 + Commit**

Run: `.venv/bin/python -m pytest -q`
Expected: 全綠

```bash
git add agent_template/core/__init__.py examples/agent.py tests/test_example_agent.py README.md docs/superpowers/specs/2026-07-11-mandatory-auth-hook-design.md
git commit -m "docs(auth): document mandatory auth, update example to context-based identity

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- 強制 API 注入 → Task 3(`assemble_middleware` 咽喉點)。
- 入口 auth(before agent)+ raise → Task 2(`AuthMiddleware`)。
- per-tool auth 提升為強制自動注入 → Task 3(`HookMiddleware([AuthHook, *hooks])`)。
- 身分來自 context → Task 1(`AuthContext`)+ Task 2(讀 `runtime.context`)+ Task 3(`context_schema`)。
- 使用者 hook 疊加在 auth 之後 → Task 3 順序 + Task 4 斷言。
- Fail-closed:缺 endpoint(build raise,Task 3)、端點錯誤/非 200(既有 client)、缺 identity(Task 2 precheck)。
- `AuthenticationError` 型別 → Task 1。
- 測試策略每點 → Task 2/3 新測試 + Task 4 對齊。
- 範例/README → Task 5。

**Placeholder scan:** 無 TBD/TODO;每個 code step 均為完整程式碼。

**Type consistency:** `assemble_middleware(config, hooks=None, observability=None)`、`AuthMiddleware(client)`、`_auth_payload(context)`、`AuthContext(identity=...)`、`AuthenticationError` 在各 task 間名稱與簽章一致;`HookMiddleware._hooks`、`create_deep_agent(context_schema=...)` 皆對照既有程式碼確認存在。
