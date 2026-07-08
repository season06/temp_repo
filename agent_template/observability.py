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
