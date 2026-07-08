import logging
import time

from langchain.agents.middleware import AgentMiddleware
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
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased


def get_logger():
    return logging.getLogger("agent_template")


def build_resource(config):
    return Resource.create({
        "service.name": config.service_name,
        "cid": config.cid or "",
        "agent.version": config.agent_version or "",
        "framework": "deepagents",
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


_state = {"handle": None, "handler": None, "providers": []}


def setup_observability(config):
    """建立 trace/metrics/log 管線並回傳 handle。o11y 關閉或設定失敗一律回傳 degraded handle,絕不 raise。
    冪等:重複呼叫回傳同一個快取的 handle,避免疊加 handler / 重複建立 providers。"""
    logger = get_logger()
    if not config.o11y_enabled:
        return Observability(False, {}, logger)
    if _state["handle"] is not None:
        return _state["handle"]  # idempotent: avoid stacked handlers / duplicate providers
    try:
        resource = build_resource(config)
        endpoint = config.otel_endpoint
        tracer_provider = TracerProvider(resource=resource, sampler=TraceIdRatioBased(config.sampling_ratio))
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        LangChainInstrumentor().instrument(tracer_provider=tracer_provider)

        reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint))
        meter_provider = MeterProvider(metric_readers=[reader], resource=resource)
        instruments = create_instruments(meter_provider.get_meter("agent_template"))

        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint)))
        handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
        logger.addHandler(handler)

        handle = Observability(True, instruments, logger)
        _state["handle"] = handle
        _state["handler"] = handler
        _state["providers"] = [tracer_provider, meter_provider, logger_provider]
        return handle
    except Exception:
        # 監控設定失敗絕不影響 main agent
        return Observability(False, {}, logger)


def shutdown_observability():
    """拆除 o11y 管線(移除 log handler、關閉 providers、uninstrument),並重置狀態。供 app 生命週期/測試使用。"""
    try:
        if _state["handler"] is not None:
            get_logger().removeHandler(_state["handler"])
        for provider in _state["providers"]:
            try:
                provider.shutdown()
            except Exception:
                pass
        try:
            LangChainInstrumentor().uninstrument()
        except Exception:
            pass
    finally:
        _state["handle"] = None
        _state["handler"] = None
        _state["providers"] = []


class ObservabilityMiddleware(AgentMiddleware):
    """在 tool/model/agent 邊界記錄 metrics 與 log。每次記錄都 fail-safe,永不影響 main agent。
    instruments 為空(o11y 關閉)時全部 no-op。"""

    def __init__(self, instruments, logger=None, model_name=None):
        super().__init__()
        self._instruments = instruments
        self._logger = logger
        self._model_name = model_name

    def wrap_tool_call(self, request, handler):
        start = time.monotonic()
        status = "ok"
        try:
            return handler(request)
        except Exception:
            status = "error"
            raise
        finally:
            self._record_tool(request, status, time.monotonic() - start)

    async def awrap_tool_call(self, request, handler):
        start = time.monotonic()
        status = "ok"
        try:
            return await handler(request)
        except Exception:
            status = "error"
            raise
        finally:
            self._record_tool(request, status, time.monotonic() - start)

    def after_model(self, state, runtime):
        if self._instruments:
            try:
                last = state["messages"][-1]
                usage = getattr(last, "usage_metadata", None)
                if usage:
                    tokens = self._instruments["llm_tokens"]
                    tokens.add(usage.get("input_tokens", 0), {"type": "prompt", "model": self._model_name or ""})
                    tokens.add(usage.get("output_tokens", 0), {"type": "completion", "model": self._model_name or ""})
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

    def _record_tool(self, request, status, duration):
        if not self._instruments:
            return
        try:
            tool_name = request.tool_call["name"]
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
