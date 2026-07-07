# A2A MVP 範例

> 使用 `a2a-sdk==0.3.26`(pydantic 型別)。詳見 plan 的 Task 1 實測註記。

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
無 token 時 JSON-RPC 端點(`/`)回 401;`/.well-known/agent-card.json` 免 token 可取得。

> `call_agent.py` 會真的觸發 deepagent 推理,需 `A2A_LLM_BASE_URL` 指向可用的 OpenAI 相容 endpoint。
> 只想驗框架(auth + card + 路由)不打真 LLM,可用 `curl`(見下)或跑 `pytest tests/test_e2e.py`。

## 4. 純框架煙霧測試(不需 LLM)
```bash
curl -s http://127.0.0.1:9999/.well-known/agent-card.json          # 200,免 auth
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:9999/ \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{}}'   # 401,缺 token
```

## 5. 啟用 OpenTelemetry tracing(可選)

需先裝 otel extra:
```bash
python3 -m pip --python .venv/bin/python install \
  opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc \
  opentelemetry-instrumentation-starlette opentelemetry-instrumentation-httpx
```

設環境變數後起 server(trace 走 OTLP/gRPC):
```bash
export A2A_OTEL_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317   # 你的 collector
export A2A_OTEL_SERVICE_NAME=a2a-mvp-deepagent
.venv/bin/python examples/run_server.py
```

覆蓋範圍:入站 HTTP(Starlette)、a2a-sdk 內部分派(SDK 內建)、出站 peer 呼叫(httpx)。
同一條 trace 會透過 W3C `traceparent` 自動跨 agent 串接。

### 替代啟動法(零程式碼,auto-instrument 啟動器)
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
.venv/bin/python -m pip --python .venv/bin/python install opentelemetry-distro
.venv/bin/opentelemetry-instrument .venv/bin/python -m a2a_mvp
```

### 已知缺口
LLM / agent 推理層(deepagents/langchain/langgraph)的 span 尚未納入,走 LangChain 自身
OTel / LangSmith,留待下一階段。
