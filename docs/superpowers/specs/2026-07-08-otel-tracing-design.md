# OpenTelemetry Tracing 設計規格書

- 日期:2026-07-08
- 狀態:設計確認(待 plan 拆解)
- 分支:`ai-agent`
- 前置:建構於已完成的 `a2a_mvp` MVP 之上(A2A server + JWT auth + deepagent)

## 目的

為 `a2a_mvp` 加上 **OpenTelemetry 分散式追蹤(distributed tracing)**,讓一次 A2A 請求從入站 HTTP、認證、a2a-sdk 分派、到出站 peer 呼叫的路徑可被觀測。

本階段目標為 **「打通管線」**:裝好 OTel SDK + OTLP exporter,靠現成 auto-instrumentation 套件與 a2a-sdk 內建 span 取得覆蓋,盡量不改動既有商業邏輯碼。

## 範圍與前提

- **策略:混合(hybrid)。** 有現成 auto-instrument 套件的層直接用;a2a-sdk 內建 `@trace_class` 靠設定全域 provider 免費啟動;沒有現成套件的自行控管。
- **Exporter:** OTLP over **gRPC(4317)**,endpoint 走標準環境變數 `OTEL_EXPORTER_OTLP_ENDPOINT`。
- **預設關閉:** 以 `config.otel_enabled` 為總開關,預設 `False`。既有 20 個測試完全不受影響。
- **不打真後端測試:** 驗收用 `InMemorySpanExporter` 斷言 span 真的產生。

### 環境注意

沿用 MVP 既有做法:系統 Python 3.14 externally-managed、`.venv` 無 pip。以 host pip 灌:`python3 -m pip --python .venv/bin/python install <pkg>`。測試一律 `.venv/bin/python -m pytest`。

## 架構總覽

```
peer ─HTTP─▶ [StarletteInstrumentor 入站 span]
                        │
                        ▼
                [AuthMiddleware(JWT)]
                        │
                        ▼
        [a2a-sdk 內建 @trace_class span:handler/executor 分派]
                        │
                        ▼
                [DeepAgentExecutor.execute]
                        │  call_remote_agent tool
                        ▼
        [HTTPXClientInstrumentor 出站 span] ── call_peer ──▶ peer A2A agent
```

### Instrumentation 分層

| 層 | 手段 | 現成套件 |
|---|---|---|
| 入站 HTTP | `StarletteInstrumentor().instrument_app(app)` | `opentelemetry-instrumentation-starlette` |
| 出站 HTTP(`call_peer`) | `HTTPXClientInstrumentor().instrument()` | `opentelemetry-instrumentation-httpx` |
| a2a-sdk 內部分派 | 設全域 `TracerProvider` 即自動啟動 | SDK 內建 `a2a.utils.telemetry`(`@trace_class`) |
| 我們的 middleware / tool | 落在入站 span 內,本階段不加自訂 span | 自控(暫不做) |
| LLM / agent 推理(deepagents/langchain) | **已知缺口**,走 LangChain 自身 OTel / LangSmith | 下一階段 |

## 元件契約

| 元件 | 職責 | 對外介面 |
|---|---|---|
| `telemetry.py` | 建立 TracerProvider + OTLP exporter + 全域註冊;instrument httpx;提供 app instrument helper | `configure_tracing(config, span_exporter=None)`、`instrument_app(app, config)` |
| `config.py`(擴充) | 新增 otel 三欄位與 env 讀取 | `Config.otel_enabled / otel_service_name / otel_exporter_endpoint` |
| `server/app.py`(修改) | `otel_enabled` 時對 built app 做 `instrument_app` | `build_app(config, model=None)` 不變簽名 |
| `__main__.py` / `examples/run_server.py`(修改) | `build_app` 前先 `configure_tracing(config)` | 進入點 |

### `telemetry.py` 介面細節

- `configure_tracing(config, span_exporter=None)`
  - `config.otel_enabled` 為 `False` → 直接 `return None`(no-op)。
  - 建 `Resource`,`service.name = config.otel_service_name`。
  - 建 `TracerProvider(resource=...)`,加 span processor:
    - 有傳 `span_exporter`(測試)→ `SimpleSpanProcessor(span_exporter)`。
    - 否則 → `BatchSpanProcessor(OTLPSpanExporter(endpoint=... 或不傳讓 SDK 讀標準 env))`。
  - `trace.set_tracer_provider(provider)`。
  - `HTTPXClientInstrumentor().instrument()`(出站,全域)。
  - 內部 guard(module-level flag)確保只設定一次;重入回傳既有 provider。
  - 回傳 `provider`(供測試取用)。
- `instrument_app(app, config)`
  - `config.otel_enabled` 為 `True` → `StarletteInstrumentor().instrument_app(app)`;否則 no-op。

### `Config` 新增欄位

| 欄位 | 型別/預設 | env |
|---|---|---|
| `otel_enabled` | `bool = False` | `A2A_OTEL_ENABLED`(`true`/`1` 為真) |
| `otel_service_name` | `str = "a2a-mvp-deepagent"` | `A2A_OTEL_SERVICE_NAME` |
| `otel_exporter_endpoint` | `str = ""` | `OTEL_EXPORTER_OTLP_ENDPOINT`(空→exporter 用預設 `localhost:4317`) |

## 資料流

1. 進入點呼叫 `configure_tracing(config)`:設全域 provider、掛 OTLP gRPC exporter、instrument httpx。
2. `build_app` 建好 Starlette app 後,`otel_enabled` 時 `instrument_app(app, config)`。
3. 請求進來:StarletteInstrumentor 開一個 HTTP server root span;a2a-sdk 分派方法(已被 `@trace_class` 裝飾)在其下開子 span;`call_peer` 內的 httpx 呼叫開 client 子 span。
4. span 經 BatchSpanProcessor 以 OTLP/gRPC 送到 collector。

## 錯誤處理

- **未裝 OTel 套件卻設 `otel_enabled=True`:** `configure_tracing` import 失敗 → 記 warning 並降級為 no-op,不讓 server 起不來。
- **collector 不可達:** OTLP BatchSpanProcessor 內部非阻塞、失敗僅記 log,不影響請求處理。
- **重複設定 provider:** 由 module guard 擋下,避免 OTel「provider already set」warning。

## 測試策略

`tests/test_telemetry.py`(不打真 collector):

- `test_disabled_is_noop`:`configure_tracing(Config())` 回 `None`;`build_app` 預設不 instrument;`GET card` 仍 200。
- `test_spans_exported_with_inmemory`:`otel_enabled=True` + 注入 `InMemorySpanExporter`;經 `TestClient` 打 card 與帶 token 的 rpc;斷言 `exporter.get_finished_spans()` 非空,且含一個 HTTP server span。此為「管線打通」驗收證據。

> 注意 OTel 全域 provider 一個 process 只能設一次:測試以單一整合測試涵蓋 export 路徑,並在 `configure_tracing` 內以 guard 容忍重入。

## 文件

`examples/README.md` 新增:

- 「啟用 OTel」段:`export A2A_OTEL_ENABLED=true`、`export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317`,再起 server。
- 替代啟動法(hybrid 精神):`opentelemetry-instrument .venv/bin/python -m a2a_mvp`。
- 標註已知缺口:LLM/agent 層 trace 留待下一階段。

## 相依套件

放進 `pyproject.toml` 的 optional extra `otel`,核心不強制安裝:

- `opentelemetry-sdk`
- `opentelemetry-exporter-otlp-proto-grpc`
- `opentelemetry-instrumentation-starlette`
- `opentelemetry-instrumentation-httpx`

(`opentelemetry-api`、`opentelemetry-semantic-conventions`、`grpcio`、`wrapt`、`asgiref` 為轉移相依,已驗證無版本衝突。)

## Non-goals(本階段明確不做)

- LLM / agent 推理層(deepagents/langchain/langgraph)的 span —— 走 LangChain 自身 OTel / LangSmith,下一階段。
- Metrics 與 logs 關聯(僅 tracing)。
- 自訂商業 span(auth / tool 細節),本階段靠既有 span 覆蓋即可。
- 取樣策略調整與自訂 baggage 傳遞(留待需要時再加)。

> 註:W3C `traceparent` 的跨 A2A 傳遞是**免費**的——`HTTPXClientInstrumentor` 出站自動注入、`StarletteInstrumentor` 入站自動萃取,故同一條 trace 可跨 agent 串接,無需額外程式碼。
