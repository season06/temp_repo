# 第三階段: A2A

給 agent 加上 A2A 殼:server 側把自己的 agent 曝露成 A2A 端點,client 側把遠端 A2A agent
當成 tool 使用。兩側都做。

## Server 側

### API

```python
agent = AgentBuilder("config.yaml").build()
agent.serve(host="0.0.0.0", port=9000)   # 一行起服務(內部 uvicorn.run,阻塞)
```

- `agent.a2a_app()` 回傳 ASGI app(逃生口):掛進既有 FastAPI/Starlette、
  `uvicorn app:app --workers N` 自控部署、測試用 ASGITransport 直打
- `serve()` 內部就是 `uvicorn.run(self.a2a_app(), ...)`

### 回應語義

- Agent Card 宣告 `streaming=True`
- executor 以原生 agent 的 `astream` 推事件——**一套實作同時支援**
  `message/send`(一次拿完整結果)與 `message/stream`(逐段收),由呼叫端決定

### Authentication(留殼,等 auth spec)

- executor 收可選 `auth`(async callable):回 False → 回應 "unauthorized"
- 預設 None = 不驗;auth spec 定案後填肉,骨架不動

## Agent Card

- card 內容是**獨立檔案**(`agent_card.yaml` / `agent_card.json`),不與 config.yaml 合併
- config.yaml 只有一個**可選的路徑指標**:`agent_card: "./cards/my_card.yaml"`
  (相對 config 目錄解析);不寫則預設找 config 同目錄的 `agent_card.yaml`,再找 `agent_card.json`
- registry zip 內含 `agent_card.yaml` = remote 有提供 → **整檔以 remote 為準**
  (logger info,不發 warning)
- **local 與 remote 都沒有 card 檔 → `serve()` / `a2a_app()` 直接報錯**
  (人話訊息:請建立 agent_card.yaml);純 invoke 使用者不受影響
- local card 檔解析失敗 → fail fast(同 config 打錯字語義)
- remote card 解析失敗 → warning + fallback local card(同 remote config 爛資料語義)

### Schema

```yaml
name: my-agent          # 必填
description: ""         # 預設空字串
version: "0.1.0"        # 預設 "0.1.0"
url:                    # card 對外宣告位址;沒填由 serve() 的 host/port 推 http://{host}:{port}
skills:                 # 可選;沒填給預設單一 "chat" skill
  - id: chat
    name: Chat
    description: Converse with the agent.
    tags: [chat]
```

## Client 側

### config

```yaml
local_a2a:
  - name: research-agent
    url: http://other-host:9000
```

- build 時**一律抓** Agent Card(`/.well-known/agent-card.json`),
  tool description 用 card 的;抓不到 → warning + 跳過該 agent(同 mcp 語義)
- 每個 entry 包成一個 langchain tool:tool 內部送 message 給遠端 agent、回最終文字
- tool 對 LLM 固定一次性呼叫(tool 必須回完整字串,串流無意義)
- a2a tool 進既有 dedupe 鏈,位置排在 local 來源之後
  (優先序:remote mcp > local tools/mcp > a2a)
- 內部「打 A2A 端點」的 async 函式公開當 helper,並留 `headers` 參數(預設 None,auth 殼)
- registry 的 remote config **不**加 a2a 宣告(future)

## 依賴與結構

- 依賴新增:`a2a-sdk`、`uvicorn`(protobuf 相容性實作時實測;舊分支曾需降 6.x)
- 模組:
  - `a2a/card.py`——card 檔解析/驗證,local + remote 衝突規則
  - `a2a/executor.py`——AgentA2AExecutor:接原生 agent 的 astream 推事件;auth 殼
  - `a2a/server.py`——AgentCard 組裝 + routes + build ASGI app
  - `loaders/a2a.py`——client 側:card 抓取 + 包成 tool + call helper
  - `core/agent.py` 加 `serve()` / `a2a_app()`
- example:`agent_card.yaml` 範例 + `serve.py` 一行起服務範例

## 第四階段(本期不做)

- A2A 入站/出站認證(等 auth spec)
- registry remote config 宣告 a2a
- a2a tool 的串流轉發
