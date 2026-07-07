# A2A + Auth DeepAgent MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建一個最小 deepagent,以官方 `a2a-sdk` 對外暴露成 A2A server(JWT 入站 auth)並能以 client 呼叫別的 A2A agent。

**Architecture:** Starlette ASGI 承載 a2a-sdk 的 JSON-RPC + Agent Card 路由;JWT 驗證做成 **ASGI middleware**(非 deepagents `AgentMiddleware`),驗完把 principal 寫進 contextvar 供 executor / tool 讀取;deepagent 由 `create_deep_agent` 建,工具含一個本地 tool 與一個對外呼叫 peer 的 `call_remote_agent`。

**Tech Stack:** Python 3.14 (`.venv`)、a2a-sdk 1.x、Starlette、uvicorn、httpx、PyJWT[crypto]、deepagents、langchain-openai、langgraph、pytest、pytest-httpx。

## Global Constraints

- **型別註記(專案慣例):** 只標註 `dict` / `list`;不 import `typing`、不標註 primitive、不標註回傳為 primitive 的函式。
- **venv 安裝法:** 系統 Python 3.14 externally-managed 且 venv 無 pip。以 host pip 灌:`python3 -m pip --python .venv/bin/python install <pkg>`(`--python` 放 `install` 之前)。**不要**跑裸 `pip install`。
- **測試指令:** 一律 `.venv/bin/python -m pytest`(repo 根;`tests/` 為 package)。
- **套件名:** `a2a_mvp`。
- **SDK 符號真實性:** a2a-sdk 各版符號有差異。Task 1 會跑 API 探針確認 1.x 真實 import 路徑;**後續任務若 import 失敗,以探針輸出為準替換**,SDK 耦合只在 `server/card.py`、`server/executor.py`、`server/app.py`、`a2a_client.py` 四檔。
- **不打真 LLM:** 所有測試用 stub chat model。
- **A2A 角色:** server + client 兩端。**Auth:** JWT bearer(sig/iss/aud/exp)。**LLM:** 可配置 OpenAI 相容 endpoint。

---

### Task 1: 專案骨架、環境、相依與 SDK API 探針

**Files:**
- Create: `pyproject.toml`(改寫既有)、`a2a_mvp/__init__.py`、`a2a_mvp/config.py`、`a2a_mvp/server/__init__.py`、`tests/__init__.py`、`tests/test_config.py`
- Create(暫存):`scratch_api_probe.py`(探針,驗完刪)

**Interfaces:**
- Produces: `a2a_mvp.config.Config`(frozen dataclass,欄位見下)、`Config.from_env()`

- [ ] **Step 1: 建 venv 並安裝相依**

```bash
python3 -m venv .venv
python3 -m pip --python .venv/bin/python install \
  "a2a-sdk==1.1.0" starlette uvicorn httpx "pyjwt[crypto]" \
  deepagents langchain-openai langgraph pytest pytest-httpx
```

Expected: 全部安裝成功。若 a2a-sdk 1.1.0 相依衝突,退到 `a2a-sdk==0.3.26` 並在此註記所選版本。

- [ ] **Step 2: SDK API 探針(確認真實 import 路徑)**

建 `scratch_api_probe.py`:

```python
import a2a, pkgutil, importlib

def dump(modname):
    try:
        m = importlib.import_module(modname)
    except Exception as e:
        print(f"[skip] {modname}: {e}")
        return
    names = [n for n in dir(m) if not n.startswith("_")]
    print(f"== {modname} ==")
    print(", ".join(names))

for modname in [
    "a2a.server.agent_execution",
    "a2a.server.request_handlers",
    "a2a.server.routes",
    "a2a.server.tasks",
    "a2a.server.events",
    "a2a.types",
    "a2a.client",
    "a2a.utils",
    "a2a.helpers",
]:
    dump(modname)
```

Run: `.venv/bin/python scratch_api_probe.py`
Expected: 印出各模組真實符號。**把確認到的下列符號記在本任務下方**(供 Task 4–9 引用):Agent Card 建構型別、`AgentExecutor`/`RequestContext`/`EventQueue`、request handler、route 工廠或 `A2AStarletteApplication`、`InMemoryTaskStore`、client 建構、以及「取訊息文字」與「送 agent 文字回應」的 helper。刪除 `scratch_api_probe.py`。

- [ ] **Step 3: 寫 config 失敗測試**

`tests/test_config.py`:

```python
import os
from a2a_mvp.config import Config


def test_from_env_reads_all_fields(monkeypatch):
    monkeypatch.setenv("A2A_LLM_BASE_URL", "http://llm.local/v1")
    monkeypatch.setenv("A2A_LLM_API_KEY", "sk-x")
    monkeypatch.setenv("A2A_LLM_MODEL", "qwen-max")
    monkeypatch.setenv("A2A_JWT_ISSUER", "https://issuer")
    monkeypatch.setenv("A2A_JWT_AUDIENCE", "a2a-mvp")
    monkeypatch.setenv("A2A_JWT_ALGORITHMS", "HS256")
    monkeypatch.setenv("A2A_JWT_SECRET", "topsecret")
    monkeypatch.setenv("A2A_ALLOWED_REMOTE_AGENTS", "http://peer.local,http://peer2.local")
    cfg = Config.from_env()
    assert cfg.llm_model == "qwen-max"
    assert cfg.jwt_audience == "a2a-mvp"
    assert cfg.jwt_algorithms == ["HS256"]
    assert "http://peer.local" in cfg.allowed_remote_agents


def test_defaults_when_optional_missing(monkeypatch):
    for k in list(os.environ):
        if k.startswith("A2A_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("A2A_JWT_SECRET", "s")
    cfg = Config.from_env()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 9999
    assert cfg.jwt_algorithms == ["HS256"]
```

- [ ] **Step 4: 跑測試確認 fail**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL(`ModuleNotFoundError: a2a_mvp.config`)

- [ ] **Step 5: 實作 config**

`a2a_mvp/config.py`:

```python
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "not-needed"
    llm_model: str = "qwen2.5"
    jwt_issuer: str = "https://issuer.local"
    jwt_audience: str = "a2a-mvp"
    jwt_algorithms: list = field(default_factory=lambda: ["HS256"])
    jwt_secret: str = ""          # HS256 用;RS256 時改用 jwt_jwks_url / jwt_public_key
    jwt_jwks_url: str = ""
    jwt_public_key: str = ""
    host: str = "127.0.0.1"
    port: int = 9999
    public_url: str = "http://127.0.0.1:9999"
    allowed_remote_agents: list = field(default_factory=list)
    outbound_service_token: str = ""   # 出站呼叫 peer 帶的服務憑證

    @classmethod
    def from_env(cls):
        algos = os.environ.get("A2A_JWT_ALGORITHMS", "HS256")
        remotes = os.environ.get("A2A_ALLOWED_REMOTE_AGENTS", "")
        return cls(
            llm_base_url=os.environ.get("A2A_LLM_BASE_URL", cls.llm_base_url),
            llm_api_key=os.environ.get("A2A_LLM_API_KEY", cls.llm_api_key),
            llm_model=os.environ.get("A2A_LLM_MODEL", cls.llm_model),
            jwt_issuer=os.environ.get("A2A_JWT_ISSUER", cls.jwt_issuer),
            jwt_audience=os.environ.get("A2A_JWT_AUDIENCE", cls.jwt_audience),
            jwt_algorithms=[a.strip() for a in algos.split(",") if a.strip()],
            jwt_secret=os.environ.get("A2A_JWT_SECRET", ""),
            jwt_jwks_url=os.environ.get("A2A_JWT_JWKS_URL", ""),
            jwt_public_key=os.environ.get("A2A_JWT_PUBLIC_KEY", ""),
            host=os.environ.get("A2A_HOST", cls.host),
            port=int(os.environ.get("A2A_PORT", cls.port)),
            public_url=os.environ.get("A2A_PUBLIC_URL", cls.public_url),
            allowed_remote_agents=[r.strip() for r in remotes.split(",") if r.strip()],
            outbound_service_token=os.environ.get("A2A_OUTBOUND_SERVICE_TOKEN", ""),
        )
```

也建空的 `a2a_mvp/__init__.py`、`a2a_mvp/server/__init__.py`、`tests/__init__.py`。

- [ ] **Step 6: 跑測試確認 pass**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml a2a_mvp/ tests/__init__.py tests/test_config.py
git commit -m "feat(mvp): scaffold a2a_mvp package + Config; confirm a2a-sdk API"
```

---

### Task 2: JWT 驗證與 Principal

**Files:**
- Create: `a2a_mvp/server/auth.py`、`tests/test_auth.py`(本任務只測 `verify_token`)

**Interfaces:**
- Consumes: `Config`(jwt_* 欄位)
- Produces: `Principal`(frozen dataclass:`subject`、`claims`(dict))、`verify_token(token, config) -> Principal`(失敗 raise `AuthError`)、`AuthError(Exception)`

- [ ] **Step 1: 寫失敗測試**

`tests/test_auth.py`:

```python
import time
import jwt
import pytest
from a2a_mvp.config import Config
from a2a_mvp.server.auth import verify_token, AuthError

CFG = Config(jwt_secret="testsecret", jwt_issuer="https://issuer.local",
             jwt_audience="a2a-mvp", jwt_algorithms=["HS256"])


def _mint(**over):
    claims = {"sub": "peer-agent", "iss": "https://issuer.local",
              "aud": "a2a-mvp", "exp": int(time.time()) + 60}
    claims.update(over)
    return jwt.encode(claims, "testsecret", algorithm="HS256")


def test_valid_token_returns_principal():
    p = verify_token(_mint(), CFG)
    assert p.subject == "peer-agent"


def test_expired_token_rejected():
    with pytest.raises(AuthError):
        verify_token(_mint(exp=int(time.time()) - 10), CFG)


def test_wrong_audience_rejected():
    with pytest.raises(AuthError):
        verify_token(_mint(aud="someone-else"), CFG)


def test_wrong_issuer_rejected():
    with pytest.raises(AuthError):
        verify_token(_mint(iss="https://evil"), CFG)


def test_bad_signature_rejected():
    bad = jwt.encode({"sub": "x", "iss": "https://issuer.local",
                      "aud": "a2a-mvp", "exp": int(time.time()) + 60},
                     "WRONGKEY", algorithm="HS256")
    with pytest.raises(AuthError):
        verify_token(bad, CFG)
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `.venv/bin/python -m pytest tests/test_auth.py -v`
Expected: FAIL(`ModuleNotFoundError: a2a_mvp.server.auth`)

- [ ] **Step 3: 實作 verify_token**

`a2a_mvp/server/auth.py`(本任務先加驗證部分):

```python
from dataclasses import dataclass, field
import jwt
from jwt import PyJWKClient


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    subject: str
    claims: dict = field(default_factory=dict)


def _signing_key(token, config):
    if config.jwt_jwks_url:
        return PyJWKClient(config.jwt_jwks_url).get_signing_key_from_jwt(token).key
    if config.jwt_public_key:
        return config.jwt_public_key
    return config.jwt_secret


def verify_token(token, config):
    try:
        claims = jwt.decode(
            token,
            _signing_key(token, config),
            algorithms=config.jwt_algorithms,
            audience=config.jwt_audience,
            issuer=config.jwt_issuer,
            options={"require": ["exp", "iss", "aud"]},
        )
    except Exception as exc:
        raise AuthError("invalid token") from exc
    return Principal(subject=claims.get("sub", ""), claims=claims)
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `.venv/bin/python -m pytest tests/test_auth.py -v`
Expected: PASS(5 passed)

- [ ] **Step 5: Commit**

```bash
git add a2a_mvp/server/auth.py tests/test_auth.py
git commit -m "feat(mvp): JWT verify_token + Principal (HS256/RS256/JWKS)"
```

---

### Task 3: AuthMiddleware(ASGI)與 principal contextvar

**Files:**
- Modify: `a2a_mvp/server/auth.py`(加 middleware + contextvar)
- Create: `tests/test_auth_middleware.py`

**Interfaces:**
- Consumes: `verify_token`、`AuthError`、`Principal`、`Config`
- Produces: `AuthMiddleware`(Starlette `BaseHTTPMiddleware` 子類;建構參數 `app, config, exempt_paths`)、`current_principal()`(讀 contextvar,無則 None)

- [ ] **Step 1: 寫失敗測試**

`tests/test_auth_middleware.py`:

```python
import time
import jwt
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from a2a_mvp.config import Config
from a2a_mvp.server.auth import AuthMiddleware, current_principal

CFG = Config(jwt_secret="s", jwt_issuer="https://issuer.local",
             jwt_audience="a2a-mvp", jwt_algorithms=["HS256"])


def _mint():
    return jwt.encode({"sub": "peer", "iss": "https://issuer.local",
                       "aud": "a2a-mvp", "exp": int(time.time()) + 60},
                      "s", algorithm="HS256")


def _app():
    async def whoami(request):
        p = current_principal()
        return JSONResponse({"sub": p.subject if p else None})

    async def card(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/rpc", whoami, methods=["POST"]),
                            Route("/.well-known/agent-card.json", card)])
    app.add_middleware(AuthMiddleware, config=CFG,
                       exempt_paths=["/.well-known/agent-card.json"])
    return TestClient(app)


def test_missing_token_401():
    r = _app().post("/rpc")
    assert r.status_code == 401
    assert r.headers["www-authenticate"].lower().startswith("bearer")


def test_valid_token_sets_principal():
    r = _app().post("/rpc", headers={"Authorization": f"Bearer {_mint()}"})
    assert r.status_code == 200
    assert r.json()["sub"] == "peer"


def test_card_path_exempt():
    r = _app().get("/.well-known/agent-card.json")
    assert r.status_code == 200
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `.venv/bin/python -m pytest tests/test_auth_middleware.py -v`
Expected: FAIL(`ImportError: cannot import name 'AuthMiddleware'`)

- [ ] **Step 3: 實作 middleware + contextvar**

在 `a2a_mvp/server/auth.py` 追加:

```python
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

_principal_var = ContextVar("a2a_principal", default=None)


def current_principal():
    return _principal_var.get()


def _unauthorized(detail):
    return JSONResponse({"error": detail}, status_code=401,
                        headers={"WWW-Authenticate": "Bearer"})


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config, exempt_paths=None):
        super().__init__(app)
        self.config = config
        self.exempt_paths = set(exempt_paths or [])

    async def dispatch(self, request, call_next):
        if request.url.path in self.exempt_paths:
            return await call_next(request)
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return _unauthorized("missing bearer token")
        try:
            principal = verify_token(header[7:], self.config)
        except AuthError:
            return _unauthorized("invalid token")
        token = _principal_var.set(principal)
        try:
            return await call_next(request)
        finally:
            _principal_var.reset(token)
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `.venv/bin/python -m pytest tests/test_auth_middleware.py -v`
Expected: PASS(3 passed)

- [ ] **Step 5: Commit**

```bash
git add a2a_mvp/server/auth.py tests/test_auth_middleware.py
git commit -m "feat(mvp): AuthMiddleware (ASGI) + principal contextvar; card path exempt"
```

---

### Task 4: Agent Card

**Files:**
- Create: `a2a_mvp/server/card.py`、`tests/test_card.py`

**Interfaces:**
- Consumes: `Config`、Task 1 探針確認的 `a2a.types` 型別(`AgentCard`/`AgentSkill`/`AgentCapabilities`)
- Produces: `build_agent_card(config) -> AgentCard`(含至少一個 skill;`capabilities.streaming=False`;宣告 bearer 型 `securitySchemes` 與 `security` 需求)

- [ ] **Step 1: 寫失敗測試**

`tests/test_card.py`(以「可序列化 + 廣告 bearer scheme」為斷言,避開版本細節):

```python
from a2a_mvp.config import Config
from a2a_mvp.server.card import build_agent_card

CFG = Config(public_url="http://127.0.0.1:9999")


def test_card_has_identity_and_skill():
    card = build_agent_card(CFG)
    data = card.model_dump(by_alias=True, exclude_none=True)
    assert data["url"].startswith("http://127.0.0.1:9999")
    assert data["capabilities"]["streaming"] is False
    assert len(data["skills"]) >= 1


def test_card_advertises_bearer_security():
    data = build_agent_card(CFG).model_dump(by_alias=True, exclude_none=True)
    schemes = data.get("securitySchemes", {})
    dumped = str(schemes).lower()
    assert "bearer" in dumped or "http" in dumped
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `.venv/bin/python -m pytest tests/test_card.py -v`
Expected: FAIL(`ModuleNotFoundError: a2a_mvp.server.card`)

- [ ] **Step 3: 實作 build_agent_card**

`a2a_mvp/server/card.py`(import 路徑以 Task 1 探針為準;以下為 1.x 常見形狀):

```python
from a2a.types import AgentCard, AgentSkill, AgentCapabilities


def build_agent_card(config):
    skill = AgentSkill(
        id="general_assist",
        name="General Assistant",
        description="回答問題,必要時委派給其他 A2A agent。",
        tags=["assistant", "delegation"],
        examples=["幫我查這個並整理成三點"],
    )
    return AgentCard(
        name="A2A MVP DeepAgent",
        description="MVP deepagent:JWT 保護的 A2A server,兼具 client 能力。",
        url=f"{config.public_url}/",
        version="0.1.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[skill],
        security_schemes={
            "bearer": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
        },
        security=[{"bearer": []}],
    )
```

> 若探針顯示欄位名為 camelCase 或 `securitySchemes` 需用型別包裝,依探針輸出調整;斷言已寫成寬鬆比對。

- [ ] **Step 4: 跑測試確認 pass**

Run: `.venv/bin/python -m pytest tests/test_card.py -v`
Expected: PASS(2 passed)

- [ ] **Step 5: Commit**

```bash
git add a2a_mvp/server/card.py tests/test_card.py
git commit -m "feat(mvp): build_agent_card advertising bearer JWT security"
```

---

### Task 5: 出站 A2A client 與工具(本地 tool + call_remote_agent + SSRF 白名單)

**Files:**
- Create: `a2a_mvp/a2a_client.py`、`a2a_mvp/tools.py`、`tests/test_client_tool.py`

**Interfaces:**
- Consumes: `Config`(`allowed_remote_agents`、`outbound_service_token`)、Task 1 探針確認的 `a2a.client`
- Produces:
  - `a2a_client.call_peer(base_url, prompt, config) -> str`(async;帶出站 JWT;非白名單 raise `RemoteNotAllowed`)、`RemoteNotAllowed(Exception)`
  - `tools.build_tools(config) -> list`(回 LangChain tools:`echo_upper` 本地 tool + `call_remote_agent`)

- [ ] **Step 1: 寫失敗測試**

`tests/test_client_tool.py`:

```python
import asyncio
import pytest
from a2a_mvp.config import Config
from a2a_mvp.a2a_client import call_peer, RemoteNotAllowed
from a2a_mvp.tools import build_tools

CFG = Config(allowed_remote_agents=["http://peer.local"],
             outbound_service_token="svc-token")


def test_ssrf_blocklist_rejects_unlisted():
    with pytest.raises(RemoteNotAllowed):
        asyncio.run(call_peer("http://evil.local", "hi", CFG))


def test_build_tools_exposes_expected_tools():
    names = {t.name for t in build_tools(CFG)}
    assert "echo_upper" in names
    assert "call_remote_agent" in names


def test_echo_upper_local_tool():
    tool = {t.name: t for t in build_tools(CFG)}["echo_upper"]
    assert tool.invoke({"text": "abc"}) == "ABC"
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `.venv/bin/python -m pytest tests/test_client_tool.py -v`
Expected: FAIL(`ModuleNotFoundError: a2a_mvp.a2a_client`)

- [ ] **Step 3: 實作 a2a_client.call_peer**

`a2a_mvp/a2a_client.py`(client 建構/送訊以 Task 1 探針為準;下為 1.x 常見形狀):

```python
import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.utils import new_agent_text_message  # 若探針顯示不同,依探針替換


class RemoteNotAllowed(Exception):
    pass


def _check_allowed(base_url, config):
    if not any(base_url.startswith(a) for a in config.allowed_remote_agents):
        raise RemoteNotAllowed(base_url)


async def call_peer(base_url, prompt, config):
    _check_allowed(base_url, config)
    headers = {}
    if config.outbound_service_token:
        headers["Authorization"] = f"Bearer {config.outbound_service_token}"
    async with httpx.AsyncClient(headers=headers, timeout=30) as http:
        resolver = A2ACardResolver(httpx_client=http, base_url=base_url)
        card = await resolver.get_agent_card()
        client = await create_client(agent=card, client_config=ClientConfig(streaming=False))
        message = new_agent_text_message(prompt)
        chunks = []
        async for event in client.send_message(message):
            chunks.append(str(event))
        return "\n".join(chunks)
```

> `send_message` 的請求包裝與回應解析依探針調整;`call_peer` 對外契約(回字串)不變。

- [ ] **Step 4: 實作 tools**

`a2a_mvp/tools.py`:

```python
import asyncio
from langchain_core.tools import tool
from a2a_mvp.a2a_client import call_peer, RemoteNotAllowed


def build_tools(config):
    @tool
    def echo_upper(text):
        """把輸入文字轉大寫回傳(本地示範工具)。"""
        return text.upper()

    @tool
    def call_remote_agent(base_url, prompt):
        """呼叫另一個 A2A agent。base_url 須在允許清單內;回傳其文字回應。"""
        try:
            return asyncio.run(call_peer(base_url, prompt, config))
        except RemoteNotAllowed:
            return f"ERROR: remote agent not allowed: {base_url}"
        except Exception as exc:  # 逾時/遠端錯誤 → 結構化錯誤,不讓 agent crash
            return f"ERROR: remote call failed: {exc}"

    return [echo_upper, call_remote_agent]
```

- [ ] **Step 5: 跑測試確認 pass**

Run: `.venv/bin/python -m pytest tests/test_client_tool.py -v`
Expected: PASS(3 passed)

- [ ] **Step 6: Commit**

```bash
git add a2a_mvp/a2a_client.py a2a_mvp/tools.py tests/test_client_tool.py
git commit -m "feat(mvp): outbound A2A client + tools (local + call_remote_agent, SSRF allowlist)"
```

---

### Task 6: deepagent 核心

**Files:**
- Create: `a2a_mvp/agent.py`、`tests/test_agent.py`

**Interfaces:**
- Consumes: `Config`、`tools.build_tools`、deepagents `create_deep_agent`
- Produces: `build_agent(config, model=None)`(回 deepagents agent;`model=None` 時用 `ChatOpenAI` 指向 config;測試傳 stub model)、`SYSTEM_PROMPT`(module 常數)

- [ ] **Step 1: 寫失敗測試(用 stub model,不打真 LLM)**

`tests/test_agent.py`:

```python
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from a2a_mvp.config import Config
from a2a_mvp.agent import build_agent

CFG = Config()


def test_agent_runs_with_stub_model():
    stub = GenericFakeChatModel(messages=iter([AIMessage(content="hello from agent")]))
    agent = build_agent(CFG, model=stub)
    result = agent.invoke({"messages": [HumanMessage(content="hi")]})
    final = result["messages"][-1].content
    assert "hello from agent" in final
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `.venv/bin/python -m pytest tests/test_agent.py -v`
Expected: FAIL(`ModuleNotFoundError: a2a_mvp.agent`)

- [ ] **Step 3: 實作 build_agent**

`a2a_mvp/agent.py`:

```python
from deepagents import create_deep_agent
from a2a_mvp.tools import build_tools

SYSTEM_PROMPT = (
    "你是一個助理 agent。能用本地工具,必要時可用 call_remote_agent "
    "把子任務委派給其他 A2A agent。回答精簡。"
)


def build_agent(config, model=None):
    if model is None:
        from langchain_openai import ChatOpenAI
        model = ChatOpenAI(
            base_url=config.llm_base_url,
            api_key=config.llm_api_key,
            model=config.llm_model,
        )
    return create_deep_agent(
        model=model,
        tools=build_tools(config),
        system_prompt=SYSTEM_PROMPT,
    )
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `.venv/bin/python -m pytest tests/test_agent.py -v`
Expected: PASS。若 stub 因 deepagents 規劃流程需多輪回應而報「StopIteration」,改用可重複回應的 fake(`GenericFakeChatModel(messages=iter([AIMessage(content="hello from agent")]*5))`),並在此記調整。

- [ ] **Step 5: Commit**

```bash
git add a2a_mvp/agent.py tests/test_agent.py
git commit -m "feat(mvp): deepagent core (create_deep_agent + tools + system prompt)"
```

---

### Task 7: DeepAgentExecutor(A2A task ↔ deepagent 橋接)

**Files:**
- Create: `a2a_mvp/server/executor.py`、`tests/test_executor.py`

**Interfaces:**
- Consumes: `build_agent`、Task 1 探針確認的 `AgentExecutor`/`RequestContext`/`EventQueue`、取訊息與回文字的 helper、`current_principal`
- Produces: `DeepAgentExecutor(AgentExecutor)`(建構參數 `agent`;實作 `execute`、`cancel`)

- [ ] **Step 1: 寫失敗測試**

`tests/test_executor.py`(用 stub 建 agent,直接呼 execute,以 fake event queue 蒐集輸出;若探針顯示 `RequestContext`/`EventQueue` 建構方式不同,依探針調整這個測試的 harness):

```python
import asyncio
from types import SimpleNamespace
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from a2a_mvp.config import Config
from a2a_mvp.agent import build_agent
from a2a_mvp.server.executor import DeepAgentExecutor


class FakeQueue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, event):
        self.events.append(event)


def test_execute_emits_agent_text():
    stub = GenericFakeChatModel(messages=iter([AIMessage(content="bridged reply")] * 5))
    agent = build_agent(Config(), model=stub)
    ex = DeepAgentExecutor(agent)
    ctx = SimpleNamespace(message="說個回應", current_task=None)
    q = FakeQueue()
    asyncio.run(ex.execute(ctx, q))
    dumped = str(q.events)
    assert "bridged reply" in dumped
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `.venv/bin/python -m pytest tests/test_executor.py -v`
Expected: FAIL(`ModuleNotFoundError: a2a_mvp.server.executor`)

- [ ] **Step 3: 實作 executor**

`a2a_mvp/server/executor.py`(取訊息/回文字 helper 依 Task 1 探針替換;下為常見形狀。核心不變:讀文字 → invoke agent → 把最終文字 enqueue):

```python
from a2a.server.agent_execution import AgentExecutor
from a2a.utils import new_agent_text_message, get_message_text  # 依探針替換
from a2a_mvp.server.auth import current_principal


class DeepAgentExecutor(AgentExecutor):
    def __init__(self, agent):
        self.agent = agent

    async def execute(self, context, event_queue):
        query = _extract_text(context)
        principal = current_principal()
        config = {"configurable": {"principal_sub": principal.subject if principal else None}}
        result = await self.agent.ainvoke(
            {"messages": [{"role": "user", "content": query}]}, config=config
        )
        text = result["messages"][-1].content
        await event_queue.enqueue_event(new_agent_text_message(text))

    async def cancel(self, context, event_queue):
        raise NotImplementedError("cancel not supported in MVP")


def _extract_text(context):
    msg = getattr(context, "message", None)
    if msg is None:
        return ""
    try:
        return get_message_text(msg)
    except Exception:
        return str(msg)
```

> `_extract_text` 用 try/except 包住 helper,讓單元測試可傳簡單字串 message;正式路徑走真 helper。

- [ ] **Step 4: 跑測試確認 pass**

Run: `.venv/bin/python -m pytest tests/test_executor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add a2a_mvp/server/executor.py tests/test_executor.py
git commit -m "feat(mvp): DeepAgentExecutor bridging A2A task to deepagent"
```

---

### Task 8: 組 Starlette app、進入點與端到端測試

**Files:**
- Create: `a2a_mvp/server/app.py`、`a2a_mvp/__main__.py`、`tests/test_e2e.py`

**Interfaces:**
- Consumes: `build_agent`、`DeepAgentExecutor`、`build_agent_card`、`AuthMiddleware`、Task 1 探針確認的 request handler / route 工廠(或 `A2AStarletteApplication`)/ `InMemoryTaskStore`
- Produces: `build_app(config, model=None) -> Starlette`

- [ ] **Step 1: 寫失敗測試(端到端:自簽 HS256 token 過 auth,打 JSON-RPC)**

`tests/test_e2e.py`:

```python
import time
import jwt
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from starlette.testclient import TestClient
from a2a_mvp.config import Config
from a2a_mvp.server.app import build_app

CFG = Config(jwt_secret="s", jwt_issuer="https://issuer.local",
             jwt_audience="a2a-mvp", jwt_algorithms=["HS256"])


def _token():
    return jwt.encode({"sub": "peer", "iss": "https://issuer.local",
                       "aud": "a2a-mvp", "exp": int(time.time()) + 60},
                      "s", algorithm="HS256")


def _client():
    stub = GenericFakeChatModel(messages=iter([AIMessage(content="e2e reply")] * 5))
    return TestClient(build_app(CFG, model=stub))


def test_agent_card_reachable_without_auth():
    r = _client().get("/.well-known/agent-card.json")
    assert r.status_code == 200
    assert "A2A MVP DeepAgent" in r.text


def test_rpc_without_token_401():
    r = _client().post("/", json={"jsonrpc": "2.0", "id": "1",
                                  "method": "message/send", "params": {}})
    assert r.status_code == 401


def test_rpc_with_token_reaches_agent():
    body = {
        "jsonrpc": "2.0", "id": "1", "method": "message/send",
        "params": {"message": {"role": "user",
                               "parts": [{"kind": "text", "text": "hi"}],
                               "messageId": "m1"}},
    }
    r = _client().post("/", json=body, headers={"Authorization": f"Bearer {_token()}"})
    assert r.status_code == 200
    assert "e2e reply" in r.text
```

> JSON-RPC 端點路徑與 `message/send` 的 params 形狀依 Task 1 探針/實測調整;斷言聚焦「401 無 token」「200 且含 agent 回應」「card 免 auth」三個行為。

- [ ] **Step 2: 跑測試確認 fail**

Run: `.venv/bin/python -m pytest tests/test_e2e.py -v`
Expected: FAIL(`ModuleNotFoundError: a2a_mvp.server.app`)

- [ ] **Step 3: 實作 build_app**

`a2a_mvp/server/app.py`(route 佈線以 Task 1 探針為準;下為兩種常見形狀,擇一):

```python
from starlette.applications import Starlette
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a_mvp.agent import build_agent
from a2a_mvp.server.executor import DeepAgentExecutor
from a2a_mvp.server.card import build_agent_card
from a2a_mvp.server.auth import AuthMiddleware

CARD_PATH = "/.well-known/agent-card.json"


def build_app(config, model=None):
    agent = build_agent(config, model=model)
    card = build_agent_card(config)
    handler = DefaultRequestHandler(
        agent_executor=DeepAgentExecutor(agent),
        task_store=InMemoryTaskStore(),
    )

    # 形狀 A:route 工廠(1.x)
    from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
    routes = create_agent_card_routes(card=card) + create_jsonrpc_routes(handler, agent_card=card)
    app = Starlette(routes=routes)

    # 形狀 B(若探針顯示用 A2AStarletteApplication,改成):
    #   from a2a.server.apps import A2AStarletteApplication
    #   app = A2AStarletteApplication(agent_card=card, http_handler=handler).build()

    app.add_middleware(AuthMiddleware, config=config, exempt_paths=[CARD_PATH])
    return app
```

- [ ] **Step 4: 實作進入點**

`a2a_mvp/__main__.py`:

```python
import uvicorn
from a2a_mvp.config import Config
from a2a_mvp.server.app import build_app


def main():
    config = Config.from_env()
    uvicorn.run(build_app(config), host=config.host, port=config.port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 跑測試確認 pass**

Run: `.venv/bin/python -m pytest tests/test_e2e.py -v`
Expected: PASS(3 passed)。若 JSON-RPC params 形狀不符導致非 200,依探針修 `params` 後重跑。

- [ ] **Step 6: 跑全測試**

Run: `.venv/bin/python -m pytest -v`
Expected: 全數 PASS。

- [ ] **Step 7: Commit**

```bash
git add a2a_mvp/server/app.py a2a_mvp/__main__.py tests/test_e2e.py
git commit -m "feat(mvp): assemble Starlette A2A app + entrypoint + e2e (auth+card+rpc)"
```

---

### Task 9: 範例 — 起 server 與以 peer 身分互呼

**Files:**
- Create: `examples/run_server.py`、`examples/call_agent.py`、`examples/README.md`

**Interfaces:**
- Consumes: `Config`、`build_app`、Task 1 探針確認的 client 建構

- [ ] **Step 1: 寫 run_server 範例**

`examples/run_server.py`:

```python
"""起 A2A MVP server。先設環境變數(見 examples/README.md),再 python examples/run_server.py。"""
import uvicorn
from a2a_mvp.config import Config
from a2a_mvp.server.app import build_app

if __name__ == "__main__":
    cfg = Config.from_env()
    print(f"serving on http://{cfg.host}:{cfg.port}  card: {cfg.public_url}{'/.well-known/agent-card.json'}")
    uvicorn.run(build_app(cfg), host=cfg.host, port=cfg.port)
```

- [ ] **Step 2: 寫 call_agent 範例(peer 身分:自簽 JWT 呼叫我們的 server)**

`examples/call_agent.py`:

```python
"""以 peer 身分呼叫本機 server:自簽 HS256 JWT → A2A client 送 message/send。"""
import asyncio
import time
import jwt
import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.utils import new_agent_text_message  # 依 Task 1 探針替換

BASE = "http://127.0.0.1:9999"


def mint():
    return jwt.encode({"sub": "peer-cli", "iss": "https://issuer.local",
                       "aud": "a2a-mvp", "exp": int(time.time()) + 300},
                      "s", algorithm="HS256")


async def main():
    headers = {"Authorization": f"Bearer {mint()}"}
    async with httpx.AsyncClient(headers=headers, timeout=30) as http:
        card = await A2ACardResolver(httpx_client=http, base_url=BASE).get_agent_card()
        client = await create_client(agent=card, client_config=ClientConfig(streaming=False))
        async for event in client.send_message(new_agent_text_message("用一句話自我介紹")):
            print(event)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: 寫 README**

`examples/README.md`:

````markdown
# A2A MVP 範例

## 1. 設環境變數(HS256 demo,密鑰 `s`)
```bash
export A2A_JWT_SECRET=s
export A2A_JWT_ISSUER=https://issuer.local
export A2A_JWT_AUDIENCE=a2a-mvp
export A2A_LLM_BASE_URL=http://localhost:11434/v1   # 任一 OpenAI 相容 endpoint
export A2A_LLM_MODEL=qwen2.5
export A2A_ALLOWED_REMOTE_AGENTS=http://127.0.0.1:9999
```

## 2. 起 server
```bash
.venv/bin/python examples/run_server.py
```

## 3. 另開終端,以 peer 身分呼叫
```bash
.venv/bin/python examples/call_agent.py
```
無 token 時 JSON-RPC 端點回 401;`/.well-known/agent-card.json` 免 token 可取得。
````

- [ ] **Step 4: 手動煙霧測試**

Run(終端 A):`A2A_JWT_SECRET=s .venv/bin/python examples/run_server.py`
Run(終端 B):`curl -s http://127.0.0.1:9999/.well-known/agent-card.json`(應得 card JSON)
Run(終端 B):`.venv/bin/python examples/call_agent.py`(應印出 agent 回應)
Expected: card 可取得、call_agent 收到回應。若 LLM endpoint 不可用,用 stub 版驗證框架路徑亦可,記於此。

- [ ] **Step 5: Commit**

```bash
git add examples/
git commit -m "docs(mvp): runnable examples (server + peer client) with README"
```

---

## 自審筆記(對照 spec)

- **A2A server(入站):** Task 8 `build_app` + Task 7 executor + Task 4 card。✓
- **A2A client(出站 / agent↔agent):** Task 5 `call_peer` + `call_remote_agent` tool;Task 9 peer 範例。✓
- **JWT auth 為 ASGI middleware(非 AgentMiddleware):** Task 3。✓
- **principal → contextvar → executor:** Task 3 + Task 7。✓
- **Card 免 auth、RPC 需 auth:** Task 3 exempt + Task 8 e2e。✓
- **可配置 OpenAI 相容 LLM:** Task 1 config + Task 6 `ChatOpenAI`。✓
- **SSRF 白名單、出站服務憑證:** Task 5。✓
- **JWT HS256 預設、RS256/JWKS 可插:** Task 2。✓
- **streaming=False、InMemoryTaskStore:** Task 4 / Task 8。✓
- **stub model、不打真 LLM:** Task 6/7/8。✓
- **SDK 符號不確定性:** Task 1 探針集中確認,耦合限四檔,測試斷言寬鬆化。✓
```
