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
