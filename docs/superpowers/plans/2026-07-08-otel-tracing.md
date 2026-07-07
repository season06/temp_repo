# OpenTelemetry Tracing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 為既有 `a2a_mvp` 加上 OpenTelemetry 分散式追蹤(打通管線),讓入站 HTTP、a2a-sdk 分派、出站 peer 呼叫的 span 以 OTLP/gRPC 匯出到 collector。

**Architecture:** 混合策略——入站用 `StarletteInstrumentor`、出站(httpx)用 `HTTPXClientInstrumentor`、a2a-sdk 內部靠設定全域 `TracerProvider` 免費啟動其內建 `@trace_class`。新增一個單一職責模組 `a2a_mvp/telemetry.py` 做 provider bootstrap 與 app instrument,以 `config.otel_enabled`(預設關)當總開關,現有測試零影響。

**Tech Stack:** Python 3.14(`.venv`)、a2a-sdk 0.3.26、Starlette、httpx、opentelemetry-sdk 1.43、opentelemetry-exporter-otlp-proto-grpc、opentelemetry-instrumentation-starlette/httpx(0.64b0)、pytest。

## Global Constraints

- **型別註記(專案慣例):** 只標註 `dict` / `list`;不 import `typing`、不標註 primitive、不標註回傳為 primitive 的函式。
- **venv 安裝法:** 系統 Python 3.14 externally-managed 且 venv 無 pip。以 host pip 灌:`python3 -m pip --python .venv/bin/python install <pkg>`(`--python` 放 `install` 之前)。**不要**跑裸 `pip install`。
- **測試指令:** 一律 `.venv/bin/python -m pytest`(repo 根)。
- **套件名:** `a2a_mvp`(既有)。
- **OTel 預設關:** `Config.otel_enabled` 預設 `False`;所有既有測試不得受影響(不啟用即完全 no-op)。
- **Exporter:** OTLP over **gRPC(4317)**;endpoint 走標準環境變數 `OTEL_EXPORTER_OTLP_ENDPOINT`,空字串時交給 exporter 用其預設。
- **確認過的 import 路徑(0.64b0 / 1.43):**
  - `from opentelemetry import trace`
  - `from opentelemetry.sdk.resources import Resource`
  - `from opentelemetry.sdk.trace import TracerProvider`
  - `from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor`
  - `from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter`
  - `from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter`(建構參數含 `endpoint`)
  - `from opentelemetry.instrumentation.starlette import StarletteInstrumentor`(有 `instrument_app(app)`)
  - `from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor`(有 `instrument()`)

## File Structure

- `pyproject.toml`(改):新增 optional extra `otel`。
- `a2a_mvp/config.py`(改):新增 3 個 otel 欄位與 `from_env` 讀取。
- `a2a_mvp/telemetry.py`(新):`configure_tracing`、`instrument_app`。單一職責:OTel bootstrap。
- `a2a_mvp/server/app.py`(改):`build_app` 尾端依 `otel_enabled` 呼叫 `instrument_app`。
- `a2a_mvp/__main__.py`、`examples/run_server.py`(改):`build_app` 前先 `configure_tracing`。
- `tests/test_config.py`(改):加 otel 欄位斷言。
- `tests/test_telemetry.py`(新):no-op 與 InMemory-exporter 整合驗收。
- `examples/README.md`(改):啟用 OTel 說明 + 替代啟動法 + 已知缺口。

---

### Task 1: 相依與 Config otel 欄位

**Files:**
- Modify: `pyproject.toml`(加 `[project.optional-dependencies].otel`)
- Modify: `a2a_mvp/config.py`(加 3 欄位 + from_env)
- Test: `tests/test_config.py`(加斷言)

**Interfaces:**
- Consumes: 既有 `Config`(frozen dataclass)
- Produces: `Config.otel_enabled`(bool)、`Config.otel_service_name`(str)、`Config.otel_exporter_endpoint`(str);`Config.from_env()` 讀 `A2A_OTEL_ENABLED` / `A2A_OTEL_SERVICE_NAME` / `OTEL_EXPORTER_OTLP_ENDPOINT`

- [ ] **Step 1: 安裝 OTel 相依**

```bash
python3 -m pip --python .venv/bin/python install \
  opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc \
  opentelemetry-instrumentation-starlette opentelemetry-instrumentation-httpx
```

Expected: 安裝成功(opentelemetry-sdk 1.43.x、instrumentation 0.64b0、grpcio、wrapt、asgiref)。

- [ ] **Step 2: 寫失敗測試(在 `tests/test_config.py` 追加)**

```python
def test_otel_fields_default_off(monkeypatch):
    import os
    for k in list(os.environ):
        if k.startswith("A2A_") or k == "OTEL_EXPORTER_OTLP_ENDPOINT":
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("A2A_JWT_SECRET", "s")
    cfg = Config.from_env()
    assert cfg.otel_enabled is False
    assert cfg.otel_service_name == "a2a-mvp-deepagent"
    assert cfg.otel_exporter_endpoint == ""


def test_otel_fields_from_env(monkeypatch):
    monkeypatch.setenv("A2A_JWT_SECRET", "s")
    monkeypatch.setenv("A2A_OTEL_ENABLED", "true")
    monkeypatch.setenv("A2A_OTEL_SERVICE_NAME", "my-agent")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
    cfg = Config.from_env()
    assert cfg.otel_enabled is True
    assert cfg.otel_service_name == "my-agent"
    assert cfg.otel_exporter_endpoint == "http://collector:4317"
```

- [ ] **Step 3: 跑測試確認 fail**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL(`AttributeError: 'Config' object has no attribute 'otel_enabled'`)

- [ ] **Step 4: 實作 config 欄位**

在 `a2a_mvp/config.py` 的 `Config` dataclass 內,`outbound_service_token` 之後追加欄位:

```python
    otel_enabled: bool = False
    otel_service_name: str = "a2a-mvp-deepagent"
    otel_exporter_endpoint: str = ""
```

在 `from_env` 的 `return cls(...)` 內,`outbound_service_token=...` 之後追加:

```python
            otel_enabled=os.environ.get("A2A_OTEL_ENABLED", "").lower() in ("1", "true", "yes"),
            otel_service_name=os.environ.get("A2A_OTEL_SERVICE_NAME", cls.otel_service_name),
            otel_exporter_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
```

- [ ] **Step 5: 跑測試確認 pass**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS(4 passed)

- [ ] **Step 6: 加 pyproject optional extra**

在 `pyproject.toml` 的 `[project.optional-dependencies]` 區塊,把 `dev` 那行改為兩個 extra:

```toml
[project.optional-dependencies]
dev = ["pytest", "pytest-httpx"]
otel = [
    "opentelemetry-sdk",
    "opentelemetry-exporter-otlp-proto-grpc",
    "opentelemetry-instrumentation-starlette",
    "opentelemetry-instrumentation-httpx",
]
```

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml a2a_mvp/config.py tests/test_config.py
git commit -m "feat(otel): add otel config fields + optional deps extra"
```

---

### Task 2: telemetry 模組(configure_tracing + instrument_app)

**Files:**
- Create: `a2a_mvp/telemetry.py`
- Test: `tests/test_telemetry.py`(本任務只測 no-op 與 provider 建構)

**Interfaces:**
- Consumes: `Config`(otel 欄位)、Global Constraints 列出的 OTel import 路徑
- Produces:
  - `configure_tracing(config, span_exporter=None)` → 停用時回 `None`;啟用時建全域 `TracerProvider` 並回傳。有傳 `span_exporter` 用 `SimpleSpanProcessor`,否則用 `BatchSpanProcessor(OTLPSpanExporter)`。同時 `HTTPXClientInstrumentor().instrument()`。module guard 確保只設定一次。
  - `instrument_app(app, config)` → 啟用時 `StarletteInstrumentor().instrument_app(app)`,否則 no-op。

- [ ] **Step 1: 寫失敗測試**

> 重要:OTel 全域 `TracerProvider` 一個 process 只能設一次,`configure_tracing` 內有 module guard。因此**所有需要 provider 的測試共用一個 module-scope fixture 的 exporter**,以 `clear()` 隔離;不要每個測試各建 exporter(第二個會被 guard 忽略)。停用路徑的測試用 `Config()`(otel off)不碰 provider。

`tests/test_telemetry.py`:

```python
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from a2a_mvp.config import Config
from a2a_mvp.telemetry import configure_tracing

_OTEL_CFG = Config(otel_enabled=True, otel_service_name="test-agent",
                   jwt_secret="s", jwt_issuer="https://issuer.local",
                   jwt_audience="a2a-mvp", jwt_algorithms=["HS256"])


@pytest.fixture(scope="module")
def exporter():
    exp = InMemorySpanExporter()
    configure_tracing(_OTEL_CFG, span_exporter=exp)
    return exp


def test_configure_disabled_returns_none():
    assert configure_tracing(Config()) is None


def test_manual_span_exported(exporter):
    exporter.clear()
    tracer = trace.get_tracer("t")
    with tracer.start_as_current_span("manual"):
        pass
    assert "manual" in [s.name for s in exporter.get_finished_spans()]
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `.venv/bin/python -m pytest tests/test_telemetry.py -v`
Expected: FAIL(`ModuleNotFoundError: a2a_mvp.telemetry`)

- [ ] **Step 3: 實作 telemetry**

`a2a_mvp/telemetry.py`(**OTel import 一律放在函式內 lazy import**,讓未裝 otel extra 時本模組仍可被 `app.py` import,且停用時零 OTel 相依):

```python
import logging

logger = logging.getLogger(__name__)
_provider = None


def configure_tracing(config, span_exporter=None):
    global _provider
    if not config.otel_enabled:
        return None
    if _provider is not None:
        return _provider
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    except ImportError:
        logger.warning("otel_enabled 但未安裝 OpenTelemetry,tracing 停用。請裝 'otel' extra。")
        return None
    resource = Resource.create({"service.name": config.otel_service_name})
    provider = TracerProvider(resource=resource)
    if span_exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    else:
        endpoint = config.otel_exporter_endpoint or None
        exporter = OTLPSpanExporter(endpoint=endpoint) if endpoint else OTLPSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    HTTPXClientInstrumentor().instrument()
    _provider = provider
    return provider


def instrument_app(app, config):
    if not config.otel_enabled:
        return
    try:
        from opentelemetry.instrumentation.starlette import StarletteInstrumentor
    except ImportError:
        logger.warning("otel_enabled 但未安裝 OpenTelemetry,app 未 instrument。")
        return
    StarletteInstrumentor().instrument_app(app)
```

> 兩點設計:①`_provider` module guard——同 process 只建一次(OTel 全域 provider 只能設一次)。②OTel 全為 lazy import 且以 `try/except ImportError` 降級為 no-op,符合 spec 錯誤處理(未裝 OTel 卻 enabled → 記 warning 不崩)。

- [ ] **Step 4: 跑測試確認 pass**

Run: `.venv/bin/python -m pytest tests/test_telemetry.py -v`
Expected: PASS(2 passed)

- [ ] **Step 5: Commit**

```bash
git add a2a_mvp/telemetry.py tests/test_telemetry.py
git commit -m "feat(otel): telemetry bootstrap (configure_tracing + instrument_app)"
```

---

### Task 3: 佈線進 app 與進入點 + 端到端 span 驗收

**Files:**
- Modify: `a2a_mvp/server/app.py`(build_app 尾端 instrument)
- Modify: `a2a_mvp/__main__.py`(configure_tracing)
- Modify: `examples/run_server.py`(configure_tracing)
- Test: `tests/test_telemetry.py`(追加端到端測試)

**Interfaces:**
- Consumes: `configure_tracing`、`instrument_app`(Task 2)、既有 `build_app`
- Produces: `build_app` 在 `config.otel_enabled` 時對 built app 做 Starlette instrument(簽名不變:`build_app(config, model=None)`)

- [ ] **Step 1: 寫失敗測試(在 `tests/test_telemetry.py` 追加,重用 Task 2 的 `exporter` fixture)**

> 重用同一個 module-scope `exporter` fixture(共用唯一的全域 provider);先 `clear()` 隔離,再用 `_OTEL_CFG` build app 打請求。頂部追加兩個 import。

在 `tests/test_telemetry.py` 頂部 import 區追加:

```python
from starlette.testclient import TestClient
from a2a_mvp.server.app import build_app
from tests.stub import make_stub
```

追加測試函式:

```python
def test_inbound_request_produces_server_span(exporter):
    exporter.clear()
    app = build_app(_OTEL_CFG, model=make_stub("otel reply"))
    client = TestClient(app)
    r = client.get("/.well-known/agent-card.json")
    assert r.status_code == 200
    kinds = [str(s.kind) for s in exporter.get_finished_spans()]
    assert any("SERVER" in k for k in kinds)
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `.venv/bin/python -m pytest tests/test_telemetry.py::test_inbound_request_produces_server_span -v`
Expected: FAIL(無 SERVER span——`build_app` 尚未 instrument app)

- [ ] **Step 3: 佈線進 build_app**

修改 `a2a_mvp/server/app.py`:在頂部 import 追加

```python
from a2a_mvp.telemetry import instrument_app
```

在 `build_app` 的 `app.add_middleware(...)` 之後、`return app` 之前追加:

```python
    instrument_app(app, config)
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `.venv/bin/python -m pytest tests/test_telemetry.py -v`
Expected: PASS(3 passed)

- [ ] **Step 5: 佈線進進入點**

修改 `a2a_mvp/__main__.py`,在 `build_app(config)` 之前呼叫 `configure_tracing`:

```python
import uvicorn
from a2a_mvp.config import Config
from a2a_mvp.server.app import build_app
from a2a_mvp.telemetry import configure_tracing


def main():
    config = Config.from_env()
    configure_tracing(config)
    uvicorn.run(build_app(config), host=config.host, port=config.port)


if __name__ == "__main__":
    main()
```

修改 `examples/run_server.py` 同樣在 `build_app` 前加 `configure_tracing(cfg)`:

```python
"""起 A2A MVP server。先設環境變數(見 examples/README.md),再 python examples/run_server.py。"""
import uvicorn
from a2a_mvp.config import Config
from a2a_mvp.server.app import build_app
from a2a_mvp.telemetry import configure_tracing

if __name__ == "__main__":
    cfg = Config.from_env()
    configure_tracing(cfg)
    print(f"serving on http://{cfg.host}:{cfg.port}  card: {cfg.public_url}/.well-known/agent-card.json")
    uvicorn.run(build_app(cfg), host=cfg.host, port=cfg.port)
```

- [ ] **Step 6: 跑全測試確認無回歸**

Run: `.venv/bin/python -m pytest -q`
Expected: 全數 PASS(既有 20 + 新增 telemetry/config 測試)。

- [ ] **Step 7: Commit**

```bash
git add a2a_mvp/server/app.py a2a_mvp/__main__.py examples/run_server.py tests/test_telemetry.py
git commit -m "feat(otel): wire tracing into build_app + entrypoints; e2e span assertion"
```

---

### Task 4: 文件與手動煙霧驗證

**Files:**
- Modify: `examples/README.md`

**Interfaces:**
- Consumes: 完成的 otel 佈線

- [ ] **Step 1: 更新 README**

在 `examples/README.md` 末尾追加:

````markdown
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
````

- [ ] **Step 2: 手動煙霧驗證(不需真 collector)**

Run(終端 A,啟用 otel 但指向不存在的 collector,驗證 server 不崩):
```bash
A2A_OTEL_ENABLED=true A2A_JWT_SECRET=s PYTHONPATH=. \
  .venv/bin/python examples/run_server.py
```
Run(終端 B):
```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9999/.well-known/agent-card.json
```
Expected: 回 `200`;server 端不因 collector 不可達而崩潰(OTLP export 失敗僅記 log)。停掉 server。

- [ ] **Step 3: Commit**

```bash
git add examples/README.md
git commit -m "docs(otel): enable-tracing guide + launcher alt + known gap"
```

---

## 自審筆記(對照 spec)

- **打通管線(SDK 內建 + Starlette + httpx auto-instrument):** Task 2 configure_tracing 設全域 provider + instrument httpx;Task 3 instrument_app。✓
- **OTLP / gRPC(4317)、endpoint 走標準 env:** Task 1 config `otel_exporter_endpoint` 讀 `OTEL_EXPORTER_OTLP_ENDPOINT`;Task 2 `OTLPSpanExporter`。✓
- **預設關、既有測試零影響:** Task 1 `otel_enabled=False` 預設;Task 3 Step 6 全測試回歸。✓
- **InMemory exporter 驗收:** Task 2 手動 span、Task 3 SERVER span。✓
- **未裝 OTel / collector 不可達降級:** Task 4 Step 2 煙霧驗證(collector 不可達不崩)。✓
- **文件 + 替代啟動法 + 已知缺口:** Task 4。✓
- **型別註記慣例、venv 安裝法、測試指令:** Global Constraints,各任務沿用。✓
