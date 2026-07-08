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
