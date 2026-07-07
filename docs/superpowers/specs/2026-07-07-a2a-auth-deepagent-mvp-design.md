# A2A + Auth DeepAgent MVP 設計規格書

- 日期:2026-07-07
- 狀態:設計確認(待 plan 拆解)
- 分支:`ai-agent`

## 目的

提供一個最小可行(MVP)的 **deepagent**,示範兩件事:

1. **A2A 互通** — 把 deepagent 依 [A2A(Agent2Agent)協定](https://a2a-protocol.org)以 HTTP 對外暴露成 **server**,同時能以 **client** 身分呼叫別的 A2A agent(agent↔agent 互呼)。
2. **Auth middleware** — 在 A2A HTTP 入站邊界用 **JWT / OAuth2 bearer** 驗證,守住「誰能呼叫這個 agent」。

本 MVP 為**全新獨立**專案,不建構在既有 `agent_template` 安全外殼之上。

## 範圍與前提

- **A2A 角色:** Server + Client 兩端俱全。
- **Auth 機制:** JWT bearer(驗簽名 / iss / aud / exp)。
- **LLM provider:** 可配置、不綁定;預設任一 OpenAI 相容 endpoint(可指向 Qwen)。
- **協定層落地:** 官方 `a2a-sdk`(1.x),把合規風險降到最低。
- **散布模式:** 可執行的範例專案 / 套件(`a2a_mvp`),`python -m a2a_mvp` 起 server。

### 環境注意

- 工作區的 `.venv` 已不存在,需重建。系統 Python 3.14 為 externally-managed 且其 `venv` 無 pip;沿用既有做法以 host pip 灌:`python3 -m pip --python .venv/bin/python install <pkg>`(`--python` 放 `install` 之前)。測試一律 `.venv/bin/python -m pytest`。

## 兩種 middleware 的分工(核心澄清)

本設計刻意區分兩層,避免混淆:

- **A2A 入站 auth** 屬 **HTTP / ASGI 層**,必須在「請求變成 agent task 之前」就擋下 → 以 **Starlette / ASGI middleware** 實作,**不是** deepagents 的 `AgentMiddleware`。
- deepagents 原生的 `middleware=` 跑在 agent graph 內部,對入站 auth 而言太晚,不在此使用。
- auth middleware 驗完 JWT 後,把 **principal 寫進 contextvar**;executor 讀出後注入 agent 執行 context,讓對外 tool(呼叫 peer agent 時)能沿用 / 交換 token。

## 架構總覽

```
                    ┌─────────────── 我們的 deepagent (A2A Server) ───────────────┐
  peer A2A agent    │  Starlette ASGI                                             │
  ───JWT bearer───▶ │  ┌──────────────┐   ┌──────────────────┐   ┌─────────────┐ │
   message/send     │  │ AuthMiddleware│──▶│ A2A JSON-RPC      │──▶│DeepAgent-   │ │
                    │  │ (JWT 驗證)    │   │ routes + Card     │   │Executor     │ │
                    │  │ →principal    │   │ DefaultRequest-   │   │  ↓          │ │
   /.well-known/    │  └──────────────┘   │ Handler+TaskStore │   │ create_deep │ │
   agent-card.json ◀┼── (免 auth) ────────┘                   │   │ _agent      │ │
                    │                                          └───│  tools:     │ │
                    └──────────────────────────────────────────────│ local +    │─┘
                                                                    │ call_remote │
                                              ───JWT bearer(出)───▶ │ _agent tool │───▶ peer A2A agent
                                                                    └─────────────┘
```

## 元件契約

對外只有一個進入點(`python -m a2a_mvp` 起 server)。各元件單一職責、以明確介面溝通、可獨立測試。

| 元件 | 職責 | 對外介面 |
|---|---|---|
| `config.py` | frozen dataclass:LLM(base_url / api_key / model)、JWT(issuer / audience / algorithms / 靜態 key 或 jwks_url)、server(host / port)、`allowed_remote_agents` 白名單、出站服務憑證 | `Config.from_env()` |
| `server/auth.py` | JWT 驗證(PyJWT:驗 sig / iss / aud / exp)、`AuthMiddleware`(ASGI)、`principal` contextvar | `verify_token(jwt) -> Principal`;`AuthMiddleware` |
| `server/card.py` | 組 `AgentCard`:skills、`securitySchemes` = bearer JWT、`security` 需求、`capabilities`(streaming=False) | `build_agent_card(config) -> AgentCard` |
| `server/executor.py` | `DeepAgentExecutor(AgentExecutor)`:把 A2A task 訊息餵給 deepagent、把結果寫回 event queue;讀 principal 注入 run context | `execute(context, event_queue)`、`cancel(...)` |
| `server/app.py` | 組 Starlette app:card routes(免 auth)+ jsonrpc routes(需 auth),外層包 `AuthMiddleware` | `build_app(config) -> Starlette` |
| `agent.py` | 以 `create_deep_agent(model, tools, system_prompt=...)` 建 deepagent | `build_agent(config)` |
| `tools.py` | 本地示範 tool + `call_remote_agent`(A2A 出站 tool,SSRF 白名單) | LangChain tools |
| `a2a_client.py` | 出站:解析遠端 Card → `message/send` → 帶出站 JWT → 回傳文字 | `call_peer(url, prompt) -> str` |
| `__main__.py` | uvicorn 進入點 | `python -m a2a_mvp` |

### 相依的 a2a-sdk API(1.x,已驗證)

- `a2a.server.agent_execution.AgentExecutor`(基底,實作 `execute` / `cancel`)
- `a2a.server.request_handlers.DefaultRequestHandler`
- `a2a.server.routes.create_agent_card_routes`、`create_jsonrpc_routes`
- `a2a.server.tasks.InMemoryTaskStore`
- `a2a.types.{AgentCard, AgentSkill, AgentCapabilities, AgentInterface}`
- client:`a2a.client`(ClientFactory / 送 `message/send`)
- server 以 Starlette + uvicorn 承載

## 資料流

**入站(當 server)**

1. peer 帶 `Authorization: Bearer <jwt>` 送 JSON-RPC `message/send`。
2. `AuthMiddleware` 驗簽名 / iss / aud / exp:失敗回 **401 + `WWW-Authenticate: Bearer`**。
3. 成功:把 `Principal` 寫進 contextvar。
4. JSON-RPC 路由進 `DefaultRequestHandler` → `DeepAgentExecutor.execute` 讀 principal、invoke deepagent。
5. 結果以 task 完成狀態回傳。
6. `/.well-known/agent-card.json` **免 auth**(spec 對齊:公開 Card 廣告 security scheme;受保護的 extended card 才需 auth)。

**出站(當 client / agent↔agent)**

1. LLM 決定呼叫 `call_remote_agent(url, prompt)` tool。
2. tool 先查 `allowed_remote_agents` 白名單(SSRF 防護);不在白名單 → 回結構化錯誤。
3. `a2a_client` 解析遠端 Card、帶**出站 JWT** 送 `message/send`。
4. 回傳文字給 LLM 繼續推理。這即是 agent↔agent 互呼。

## 設計決策

1. **JWT 演算法:** demo 預設 **HS256 + 共享密鑰**(零金鑰基礎設施、可直接跑);verifier 可插拔到 **RS256 / JWKS URL**(PyJWT `PyJWKClient`)。
2. **出站 token:** MVP 用 config 的**服務憑證**(client-credentials 風格)帶出;預留 on-behalf-of token exchange 插拔位。
3. **Streaming:** MVP `streaming=False`,Card 如實廣告;SSE 之後再加。
4. **Task store:** 僅 `InMemoryTaskStore`。
5. **Principal 傳遞:** 以 contextvar 從 middleware 傳到 executor,再進 agent run context 供 tool 讀取。

## 錯誤處理

- **Auth:** 缺 token / 格式錯 / 過期 / iss 或 aud 不符 → 一律 401,不洩漏細節。
- **出站 tool:** 逾時(httpx timeout)、白名單擋掉、遠端錯誤 → tool 回**結構化錯誤字串**,不讓 agent crash。
- **模型 / 執行錯誤:** 對映 A2A task `failed` 狀態 + JSON-RPC error。

## 測試策略

一律使用 **stub chat model**,不打真 LLM。

- `test_auth.py`:接受合法 token;拒絕 缺 / 過期 / 錯 aud / 錯簽;Card 路徑免 auth。
- `test_card.py`:Card 可取得且廣告 bearer security scheme;capabilities 如實。
- `test_executor.py`:A2A task → agent invoke(fake chat model)。
- `test_client_tool.py`:出站 `call_remote_agent`(mock httpx);白名單擋 SSRF。
- `test_e2e.py`:peer client → auth → executor → 回應(Starlette TestClient + 自簽 HS256 token);缺 token 得 401;Card 免 token 可取得。

## 專案結構

```
a2a_mvp/
  __init__.py
  config.py
  agent.py
  tools.py
  a2a_client.py
  server/
    __init__.py
    app.py
    executor.py
    card.py
    auth.py
  __main__.py
examples/
  run_server.py       # 起 server
  call_agent.py       # 以 peer 身分:自簽 JWT,透過 A2A client 呼叫我們的 server
tests/
  test_auth.py
  test_card.py
  test_executor.py
  test_client_tool.py
  test_e2e.py
```

## 相依套件

`a2a-sdk`、`starlette`、`uvicorn`、`httpx`、`pyjwt[crypto]`、`langchain-openai`、`deepagents`、`langgraph`、`pytest`、`pytest-httpx`。

## Non-goals(本 MVP 明確不做)

- push notification、持久化 task store、多租戶、rate limiting。
- 真 OAuth2 token exchange / on-behalf-of(以配置服務憑證代替,留插拔位)。
- SSE / streaming 回應。
- 建構於既有 `agent_template` 安全外殼之上。
