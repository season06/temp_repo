# P5 — Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以 OpenTelemetry 提供 Trace / Metrics / Log 三訊號(trace 走 langchain instrumentation 自動產生、metrics/log 自建),帶 cid/agent_version 等 resource 屬性,且**監控失敗絕不影響 main agent**、可整層關閉。

**Architecture:** `setup_observability(config)` 建立 **本地** TracerProvider(OTLP 匯出)+ 用 `LangChainInstrumentor` 對 langchain/deepagents 自動追蹤、MeterProvider(自建 instruments)、LoggerProvider(OTLP log + LoggingHandler),全部包在 fail-safe 中;`o11y_enabled=False` 或設定失敗 → 回傳 degraded(no-op)handle。`ObservabilityMiddleware` 在 tool/model/agent 邊界記錄 metrics 與 log(每次記錄都 fail-safe,永遠先跑 handler)。resource 帶 `service.name`/`cid`/`agent.version`。除 langchain instrumentor 外**不設全域 provider**(降低全域狀態風險)。

**Tech Stack:** opentelemetry-sdk 1.43、opentelemetry-exporter-otlp-proto-http 1.43、openinference-instrumentation-langchain 0.1.67、langchain.agents.middleware、pytest。

## Global Constraints

- **前置**：P0–P4 完成。
- **已驗證的 OTel 事實(地基,勿臆測)**：
  - `LangChainInstrumentor().instrument(tracer_provider=tp)` 可對 deepagents 0.6.12 / langchain 1.4.8 的 agent run 自動產生完整 trace tree(LLM / TOOL / AGENT / CHAIN span)。測試後須 `LangChainInstrumentor().uninstrument()`(全域,避免測試間汙染)。
  - Metrics:`MeterProvider(metric_readers=[...], resource=...)` → `meter.create_counter/create_histogram`;測試用 `InMemoryMetricReader`。
  - Logs:`LoggerProvider(resource=...)` + `LoggingHandler(logger_provider=lp)` 掛到 logger;在 span context 內發出的 log 會**自動帶 trace_id/span_id**;測試用 `InMemoryLogRecordExporter` + `SimpleLogRecordProcessor`。
  - `AIMessage.usage_metadata` = `{"input_tokens","output_tokens","total_tokens"}`(token metrics 來源)。
  - **fail-safe 已實測**:instrument 的 counter `.add` 拋錯時,只要包在 try/except 且照跑 handler,agent 仍完成。
  - metrics middleware 於 `ainvoke` 下正常(`awrap_tool_call` 必備、`after_model`/`after_agent` 有 async fallback)。
- **確切 import 路徑(已驗證)**：
  - `from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter`
  - `from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter`
  - `from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter`
  - `from opentelemetry.sdk.trace import TracerProvider` / `from opentelemetry.sdk.trace.export import BatchSpanProcessor`
  - `from opentelemetry.sdk.metrics import MeterProvider` / `from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, InMemoryMetricReader`
  - `from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler` / `from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, InMemoryLogRecordExporter, SimpleLogRecordProcessor`
  - `from opentelemetry.sdk.resources import Resource`
  - `from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter`
- **可靠性(硬需求)**：所有 o11y 呼叫包 try/except 後吞掉,**絕不 raise 進 main path**;匯出用 Batch/Periodic(非同步);`o11y_enabled=False` → 完全 no-op。
- **新相依(已安裝,pin)**：`opentelemetry-sdk==1.43.0`、`opentelemetry-exporter-otlp-proto-http==1.43.0`、`openinference-instrumentation-langchain==0.1.67`。
- **型別註記慣例**：只標註 dict/list;不 import `typing`;不標註 primitive;plain class + `__init__`。
- **執行測試**：`.venv/bin/python -m pytest`(repo 根目錄)。
- **Commit 時機**：commit 為執行期動作,由使用者決定何時執行本計畫。

---

### Task 1: Config 補強 + o11y 相依

**Files:**
- Modify: `agent_template/config.py`
- Modify: `pyproject.toml`
- Test: `tests/test_config.py`（同檔追加）

**Interfaces:**
- Produces: `Config` 新增 `service_name`(env `AGENT_SERVICE_NAME`,預設 `"agent_template"`);`from_env` 的 `o11y_enabled` 判定拓寬:值(小寫)落在 `{"false","0","no","off"}` → False,其餘/未設 → True。

- [ ] **Step 1: 追加測試（會失敗）**

Append to `tests/test_config.py`:

```python
import pytest


@pytest.mark.parametrize("value", ["false", "False", "0", "no", "OFF", "off"])
def test_o11y_enabled_disabled_values(monkeypatch, value):
    monkeypatch.setenv("AGENT_O11Y_ENABLED", value)
    assert Config.from_env().o11y_enabled is False


@pytest.mark.parametrize("value", ["true", "1", "yes", "anything"])
def test_o11y_enabled_truthy_values(monkeypatch, value):
    monkeypatch.setenv("AGENT_O11Y_ENABLED", value)
    assert Config.from_env().o11y_enabled is True


def test_service_name_default_and_env(monkeypatch):
    monkeypatch.delenv("AGENT_SERVICE_NAME", raising=False)
    assert Config.from_env().service_name == "agent_template"
    monkeypatch.setenv("AGENT_SERVICE_NAME", "my-svc")
    assert Config.from_env().service_name == "my-svc"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_config.py -k "o11y_enabled_disabled or service_name" -v`
Expected: FAIL（`"0"`/`"no"`/`"off"` 目前會判定為 True;且 `Config` 無 `service_name`)。

- [ ] **Step 3: 修改 `Config`**

Edit `agent_template/config.py`:
- `Config.__init__` 新增參數 `service_name="agent_template"` 並存 `self.service_name = service_name`。
- `from_env`:把 `o11y_enabled` 的判定改為下面這段,並讀 `service_name`。

```python
    @classmethod
    def from_env(cls):
        ratio = os.environ.get("AGENT_OTEL_SAMPLING_RATIO")
        enabled = os.environ.get("AGENT_O11Y_ENABLED")
        return cls(
            auth_endpoint=os.environ.get("AGENT_AUTH_ENDPOINT"),
            otel_endpoint=os.environ.get("AGENT_OTEL_ENDPOINT"),
            sampling_ratio=float(ratio) if ratio is not None else 1.0,
            o11y_enabled=(enabled.strip().lower() not in ("false", "0", "no", "off")) if enabled is not None else True,
            cid=os.environ.get("AGENT_CID"),
            agent_version=os.environ.get("AGENT_VERSION"),
            service_name=os.environ.get("AGENT_SERVICE_NAME", "agent_template"),
        )
```

（`__init__` 的參數順序:在 `agent_version=None` 後新增 `service_name="agent_template"`。）

- [ ] **Step 4: 補相依到 `pyproject.toml`**

Edit `pyproject.toml` 的 `dependencies`,追加三行：

```toml
    "opentelemetry-sdk==1.43.0",
    "opentelemetry-exporter-otlp-proto-http==1.43.0",
    "openinference-instrumentation-langchain==0.1.67",
```

Verify：`.venv/bin/python -c "import opentelemetry.sdk, openinference.instrumentation.langchain; print('ok')"` → `ok`。

- [ ] **Step 5: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS（含既有 Config 案 + 新增案）。

- [ ] **Step 6: Commit**

```bash
cd /home/xizhen/文件/temp_repo
git add agent_template/config.py pyproject.toml tests/test_config.py
git commit -m "feat: broaden o11y_enabled falsy set, add service_name, pin otel deps"
```

---

### Task 2: `observability.py` — resource / instruments / setup

**Files:**
- Create: `agent_template/observability.py`
- Test: `tests/test_observability.py`

**Interfaces:**
- Produces:
  - `build_resource(config)` → OTel `Resource`(`service.name`=config.service_name、`cid`=config.cid or ""、`agent.version`=config.agent_version or "")。
  - `create_instruments(meter)` → dict:`{"tool_calls": counter("tool_calls_total"), "tool_duration": histogram("tool_call_duration_seconds"), "llm_tokens": counter("llm_tokens_total"), "agent_runs": counter("agent_runs_total")}`。
  - `get_logger()` → `logging.getLogger("agent_template")`。
  - `Observability(enabled, instruments, logger)` — 資料 handle。
  - `setup_observability(config)` → `Observability`;`o11y_enabled=False` 或設定過程拋錯 → 回傳 `enabled=False`、`instruments={}` 的 degraded handle(**永不 raise**)。啟用時:建 resource、TracerProvider+BatchSpanProcessor(OTLPSpanExporter)、`LangChainInstrumentor().instrument(tracer_provider=tp)`、MeterProvider(PeriodicExportingMetricReader(OTLPMetricExporter))、instruments、LoggerProvider+BatchLogRecordProcessor(OTLPLogExporter)+LoggingHandler 掛到 logger。**不設全域 provider**(除 instrumentor)。

- [ ] **Step 1: 寫測試（會失敗）**

Create `tests/test_observability.py`:

```python
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from agent_template.config import Config
from agent_template import observability as obs_mod
from agent_template.observability import build_resource, create_instruments, setup_observability


def _in_memory_meter():
    reader = InMemoryMetricReader()
    return MeterProvider(metric_readers=[reader]).get_meter("test"), reader


def test_build_resource_carries_attributes():
    cfg = Config(cid="proj-9", agent_version="1.2.3", service_name="svc")
    resource = build_resource(cfg)
    assert resource.attributes.get("service.name") == "svc"
    assert resource.attributes.get("cid") == "proj-9"
    assert resource.attributes.get("agent.version") == "1.2.3"


def test_create_instruments_returns_four_named():
    meter, _ = _in_memory_meter()
    instruments = create_instruments(meter)
    assert set(instruments.keys()) == {"tool_calls", "tool_duration", "llm_tokens", "agent_runs"}


def test_setup_disabled_returns_noop_handle():
    handle = setup_observability(Config(o11y_enabled=False))
    assert handle.enabled is False
    assert handle.instruments == {}


def test_setup_failure_is_swallowed(monkeypatch):
    # 讓 setup 過程拋錯 → 必須回傳 degraded handle,不可 raise
    def boom(*a, **k):
        raise RuntimeError("otel broken")

    monkeypatch.setattr(obs_mod, "TracerProvider", boom)
    handle = setup_observability(Config(o11y_enabled=True, otel_endpoint="http://localhost:4318"))
    assert handle.enabled is False


def test_setup_enabled_builds_instruments_then_uninstrument():
    from openinference.instrumentation.langchain import LangChainInstrumentor
    handle = setup_observability(Config(o11y_enabled=True, otel_endpoint="http://localhost:4318"))
    try:
        assert handle.enabled is True
        assert set(handle.instruments.keys()) == {"tool_calls", "tool_duration", "llm_tokens", "agent_runs"}
    finally:
        LangChainInstrumentor().uninstrument()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_observability.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_template.observability'`。

- [ ] **Step 3: 實作 `observability.py`**

Create `agent_template/observability.py`:

```python
import logging

from openinference.instrumentation.langchain import LangChainInstrumentor
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def get_logger():
    return logging.getLogger("agent_template")


def build_resource(config):
    return Resource.create({
        "service.name": config.service_name,
        "cid": config.cid or "",
        "agent.version": config.agent_version or "",
    })


def create_instruments(meter):
    return {
        "tool_calls": meter.create_counter("tool_calls_total"),
        "tool_duration": meter.create_histogram("tool_call_duration_seconds"),
        "llm_tokens": meter.create_counter("llm_tokens_total"),
        "agent_runs": meter.create_counter("agent_runs_total"),
    }


class Observability:
    """o11y handle:enabled 旗標、metrics instruments、logger。disabled 時 instruments 為空、全部 no-op。"""

    def __init__(self, enabled, instruments, logger):
        self.enabled = enabled
        self.instruments = instruments
        self.logger = logger


def setup_observability(config):
    """建立 trace/metrics/log 管線並回傳 handle。o11y 關閉或設定失敗一律回傳 degraded handle,絕不 raise。"""
    logger = get_logger()
    if not config.o11y_enabled:
        return Observability(False, {}, logger)
    try:
        resource = build_resource(config)
        endpoint = config.otel_endpoint

        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        LangChainInstrumentor().instrument(tracer_provider=tracer_provider)

        reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint))
        meter = MeterProvider(metric_readers=[reader], resource=resource).get_meter("agent_template")
        instruments = create_instruments(meter)

        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint)))
        logger.addHandler(LoggingHandler(level=logging.INFO, logger_provider=logger_provider))

        return Observability(True, instruments, logger)
    except Exception:
        # 監控設定失敗絕不影響 main agent
        return Observability(False, {}, logger)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_observability.py -v`
Expected: PASS（5 passed）。

> 若 `OTLPMetricExporter(endpoint=...)` 或 log exporter 對 `endpoint=None` 有意見,測試都有給 `otel_endpoint="http://localhost:4318"`,不會實際連線(Batch/Periodic 只在背景匯出時才連,setup 不連)。

- [ ] **Step 5: Commit**

```bash
cd /home/xizhen/文件/temp_repo
git add agent_template/observability.py tests/test_observability.py
git commit -m "feat: add setup_observability (trace/metrics/log, fail-safe, toggle)"
```

---

### Task 3: `ObservabilityMiddleware`（metrics + boundary logging，fail-safe）

**Files:**
- Modify: `agent_template/observability.py`
- Test: `tests/test_observability.py`（同檔追加）

**Interfaces:**
- Produces: `ObservabilityMiddleware(instruments, logger=None, model_name=None)`（`AgentMiddleware` 子類）：
  - `wrap_tool_call` / `awrap_tool_call`:量測 handler 耗時,記 `tool_calls_total{tool,status}` 與 `tool_call_duration_seconds{tool}`;handler 拋錯 status="error" 並 re-raise。記錄與 log 皆 fail-safe(try/except 吞掉),**永遠先跑/回傳 handler 結果**。
  - `after_model`:讀 `state["messages"][-1].usage_metadata` → `llm_tokens_total{type=input|output, model}`,fail-safe。
  - `after_agent`:`agent_runs_total{status="ok"}` + log,fail-safe。
  - `instruments` 為空(disabled)時全部 no-op。

- [ ] **Step 1: 追加測試（會失敗）**

Append to `tests/test_observability.py`:

```python
def test_metrics_recorded_end_to_end_under_ainvoke():
    import asyncio
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool
    from deepagents import create_deep_agent
    from agent_template.observability import ObservabilityMiddleware
    from tests.fakes import FakeToolModel

    meter, reader = _in_memory_meter()
    instruments = create_instruments(meter)

    @tool
    def ping(x: str) -> str:
        """p"""
        return "pong:" + x

    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "ping", "args": {"x": "h"}, "id": "c1"}]),
        AIMessage(content="done", usage_metadata={"input_tokens": 3, "output_tokens": 5, "total_tokens": 8}),
    ])
    mw = ObservabilityMiddleware(instruments)
    agent = create_deep_agent(model=model, tools=[ping], system_prompt="x", middleware=[mw])
    asyncio.run(agent.ainvoke({"messages": [("user", "go")]}))

    totals = {}
    for rm in reader.get_metrics_data().resource_metrics:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                totals[m.name] = sum(dp.value for dp in m.data.data_points)
    assert totals.get("tool_calls_total") == 1
    assert totals.get("agent_runs_total") == 1
    assert totals.get("llm_tokens_total") == 8  # 3 input + 5 output


def test_failing_instrument_does_not_break_agent():
    import asyncio
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool
    from deepagents import create_deep_agent
    from agent_template.observability import ObservabilityMiddleware
    from tests.fakes import FakeToolModel

    class _Boom:
        def add(self, *a, **k):
            raise RuntimeError("otel down")

        def record(self, *a, **k):
            raise RuntimeError("otel down")

    instruments = {"tool_calls": _Boom(), "tool_duration": _Boom(), "llm_tokens": _Boom(), "agent_runs": _Boom()}

    @tool
    def ping(x: str) -> str:
        """p"""
        return "pong:" + x

    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "ping", "args": {"x": "h"}, "id": "c1"}]),
        AIMessage(content="done"),
    ])
    mw = ObservabilityMiddleware(instruments)
    agent = create_deep_agent(model=model, tools=[ping], system_prompt="x", middleware=[mw])
    out = asyncio.run(agent.ainvoke({"messages": [("user", "go")]}))
    assert out["messages"][-1].content == "done"  # 監控失敗不影響 main agent


def test_disabled_instruments_noop():
    from agent_template.observability import ObservabilityMiddleware
    mw = ObservabilityMiddleware({})

    class _Req:
        tool_call = {"name": "ping", "args": {}, "id": "c1"}

    from langchain_core.messages import ToolMessage
    result = mw.wrap_tool_call(_Req(), lambda r: ToolMessage(content="ok", tool_call_id="c1", name="ping"))
    assert result.content == "ok"  # no-op passthrough
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_observability.py -k "metrics or failing_instrument or disabled_instruments" -v`
Expected: FAIL — `ImportError: cannot import name 'ObservabilityMiddleware'`。

- [ ] **Step 3: 實作 `ObservabilityMiddleware`**

在 `agent_template/observability.py` 頂端 import 區加入：

```python
import time

from langchain.agents.middleware import AgentMiddleware
```

並在檔案末端新增：

```python
class ObservabilityMiddleware(AgentMiddleware):
    """在 tool/model/agent 邊界記錄 metrics 與 log。每次記錄都 fail-safe,永不影響 main agent。
    instruments 為空(o11y 關閉)時全部 no-op。"""

    def __init__(self, instruments, logger=None, model_name=None):
        super().__init__()
        self._instruments = instruments
        self._logger = logger
        self._model_name = model_name

    def wrap_tool_call(self, request, handler):
        tool_name = request.tool_call["name"]
        start = time.monotonic()
        status = "ok"
        try:
            return handler(request)
        except Exception:
            status = "error"
            raise
        finally:
            self._record_tool(tool_name, status, time.monotonic() - start)

    async def awrap_tool_call(self, request, handler):
        tool_name = request.tool_call["name"]
        start = time.monotonic()
        status = "ok"
        try:
            return await handler(request)
        except Exception:
            status = "error"
            raise
        finally:
            self._record_tool(tool_name, status, time.monotonic() - start)

    def after_model(self, state, runtime):
        if self._instruments:
            try:
                last = state["messages"][-1]
                usage = getattr(last, "usage_metadata", None)
                if usage:
                    tokens = self._instruments["llm_tokens"]
                    tokens.add(usage.get("input_tokens", 0), {"type": "input", "model": self._model_name or ""})
                    tokens.add(usage.get("output_tokens", 0), {"type": "output", "model": self._model_name or ""})
            except Exception:
                pass
        return None

    def after_agent(self, state, runtime):
        if self._instruments:
            try:
                self._instruments["agent_runs"].add(1, {"status": "ok"})
                self._log("agent_run", status="ok")
            except Exception:
                pass
        return None

    def _record_tool(self, tool_name, status, duration):
        if not self._instruments:
            return
        try:
            self._instruments["tool_calls"].add(1, {"tool": tool_name, "status": status})
            self._instruments["tool_duration"].record(duration, {"tool": tool_name})
            self._log("tool_call", tool=tool_name, status=status)
        except Exception:
            pass

    def _log(self, event, **fields):
        if self._logger is not None:
            try:
                self._logger.info(event, extra=fields)
            except Exception:
                pass
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_observability.py -v`
Expected: PASS（Task2 5 案 + 本 Task 3 案 = 8 passed）。

- [ ] **Step 5: Commit**

```bash
cd /home/xizhen/文件/temp_repo
git add agent_template/observability.py tests/test_observability.py
git commit -m "feat: add ObservabilityMiddleware (metrics + boundary logs, fail-safe)"
```

---

### Task 4: 接線到 `build_agent` / `AgentBuilder`

**Files:**
- Modify: `agent_template/factory.py`
- Modify: `agent_template/builder.py`
- Test: `tests/test_factory.py`、`tests/test_builder.py`（同檔追加）

**Interfaces:**
- Produces:
  - `build_agent(config, hooks=None, tools=None, observability=None)` — 當 `observability` 且 `observability.enabled` → middleware 追加 `ObservabilityMiddleware(observability.instruments, observability.logger, config.model)`(接在 HookMiddleware 之後)。`observability=None` 時行為同前(向後相容)。
  - `AgentBuilder(config, skill_registry=None, observability=None)` — `build()` 把 `observability` 傳給 `build_agent`。

- [ ] **Step 1: 追加測試（會失敗）**

Append to `tests/test_factory.py`:

```python
def test_build_agent_appends_observability_middleware_when_enabled(monkeypatch):
    calls = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")

    from agent_template.observability import ObservabilityMiddleware
    from agent_template.hooks import Hook

    class _Obs:
        enabled = True
        instruments = {"tool_calls": None, "tool_duration": None, "llm_tokens": None, "agent_runs": None}
        logger = None

    cfg = AgentConfig(api_key="k", base_url="b", model="m")
    factory.build_agent(cfg, hooks=[Hook()], observability=_Obs())
    mw = calls["middleware"]
    assert any(isinstance(m, ObservabilityMiddleware) for m in mw)


def test_build_agent_no_observability_middleware_when_disabled(monkeypatch):
    calls = {}
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **k: "LLM")
    monkeypatch.setattr(factory, "create_deep_agent", lambda **k: calls.update(k) or "AGENT")

    from agent_template.observability import ObservabilityMiddleware

    class _ObsOff:
        enabled = False
        instruments = {}
        logger = None

    factory.build_agent(AgentConfig(api_key="k", base_url="b", model="m"), observability=_ObsOff())
    assert not any(isinstance(m, ObservabilityMiddleware) for m in calls["middleware"])
```

Append to `tests/test_builder.py`:

```python
def test_builder_passes_observability_to_build_agent(monkeypatch):
    captured = {}
    monkeypatch.setattr(bmod, "load_mcp_tools", lambda conns: [])
    monkeypatch.setattr(bmod, "build_agent",
                        lambda config, hooks, tools, observability=None: captured.update(obs=observability) or "AGENT")

    class _Obs:
        enabled = True
        instruments = {}
        logger = None

    obs = _Obs()
    b = AgentBuilder(_cfg(), observability=obs)
    b.build()
    assert captured["obs"] is obs
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_factory.py tests/test_builder.py -k "observability" -v`
Expected: FAIL（`build_agent` 不接受 `observability`;`AgentBuilder` 不接受 `observability`)。

- [ ] **Step 3: 修改 `factory.build_agent`**

Edit `agent_template/factory.py`:頂端 import 區加入 `from .observability import ObservabilityMiddleware`,並改寫 `build_agent`：

```python
def build_agent(config, hooks=None, tools=None, observability=None):
    """建構並回傳原生 DeepAgent 物件（執行期回歸原生,無包裝）。
    hooks: Hook 清單;tools: 額外 tools;observability: 啟用時追加 ObservabilityMiddleware。"""
    llm = _build_llm(config)
    middleware = [HookMiddleware(hooks)] if hooks else []
    if observability is not None and observability.enabled:
        middleware.append(ObservabilityMiddleware(observability.instruments, observability.logger, config.model))
    return create_deep_agent(
        model=llm,
        tools=tools or [],
        system_prompt=config.system_prompt,
        middleware=middleware,
    )
```

- [ ] **Step 4: 修改 `AgentBuilder`**

Edit `agent_template/builder.py`:`__init__` 新增 `observability=None`、存 `self._observability = observability`;`build()` 改為 `return build_agent(self._config, hooks=self._hooks, tools=tools, observability=self._observability)`。

```python
    def __init__(self, config, skill_registry=None, observability=None):
        self._config = config
        self._registry = skill_registry or MockSkillRegistry()
        self._observability = observability
        self._mcp_connections = {}
        self._skill_ids = []
        self._hooks = []
```

（`build()` 尾行改為帶 `observability=self._observability`。）

- [ ] **Step 5: 跑測試確認通過（含既有測試不退化）**

Run: `.venv/bin/python -m pytest tests/test_factory.py tests/test_builder.py -v`
Expected: PASS（既有 factory/builder 案 + 新增 3 案 全綠;`build_agent`/`AgentBuilder` 新參數具預設值,向後相容)。

- [ ] **Step 6: 跑全部測試確認整體綠**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS（P0–P4 的 63 + P5:config 新增 + observability 8 + factory 2 + builder 1 = 約 77 passed）。

- [ ] **Step 7: Commit**

```bash
cd /home/xizhen/文件/temp_repo
git add agent_template/factory.py agent_template/builder.py tests/test_factory.py tests/test_builder.py
git commit -m "feat: wire ObservabilityMiddleware into build_agent and AgentBuilder"
```

---

## 使用方式（給整合者）

```python
from agent_template.observability import setup_observability
from agent_template.builder import AgentBuilder

obs = setup_observability(config)          # 一次,app 啟動時
builder = AgentBuilder(config, observability=obs)
# ... add_hook(auth) / add_mcp / add_skill ...
agent = builder.build()
```

## Self-Review

- **Spec coverage**（req.md Feature 6）：
  - Trace:`LangChainInstrumentor` 自動全 tree(LLM/TOOL/AGENT/CHAIN),OTLP → collector,Langfuse 消費 ✅
  - Metrics:`tool_calls_total{tool,status}`、`tool_call_duration_seconds{tool}`、`llm_tokens_total{type,model}`、`agent_runs_total{status}` ✅
  - Log:OTel Logs SDK(LoggerProvider+LoggingHandler),在 span context 內自動帶 trace_id/span_id;`ObservabilityMiddleware` 在邊界發 log ✅
  - resource 帶 `cid` + `agent.version`(+ service.name) ✅
  - 後端 OTLP → otel-collector ✅
  - **監控失敗不可影響 main agent**:setup 失敗 → degraded no-op;每次記錄 try/except 吞掉;handler 永遠先跑/回傳(已實測)✅
  - 可整層關閉:`o11y_enabled=False` → no-op handle;`AGENT_O11Y_ENABLED` falsy set 已拓寬(P0 defer 補完)✅
  - 非同步匯出:BatchSpanProcessor / PeriodicExportingMetricReader / BatchLogRecordProcessor ✅
- **Placeholder scan**：無 TBD/TODO;所有 OTel API 路徑、instrumentation 於 deepagents 的可用性、metrics/log 記錄、fail-safe 皆已 spike 驗證。✅
- **Type consistency**：`setup_observability(config)`→`Observability(enabled, instruments, logger)`;`create_instruments` 的四個 key(tool_calls/tool_duration/llm_tokens/agent_runs)在 middleware 與測試一致;`ObservabilityMiddleware(instruments, logger, model_name)`;`build_agent(..., observability=None)`、`AgentBuilder(..., observability=None)` 相容既有呼叫。✅
- **Scope**:A2A(P6)不碰;a2a_call span 由 P6 的 instrumentation 自然涵蓋。取樣率(sampling_ratio)MVP 先建管線,細緻取樣策略後續。✅
- **測試衛生**:啟用 setup 的測試在 finally `LangChainInstrumentor().uninstrument()`,避免全域 instrument 汙染其他測試。✅
