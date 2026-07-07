import time

import pytest

pytest.importorskip("opentelemetry")
pytest.importorskip("opentelemetry.exporter.otlp.proto.grpc.trace_exporter")

import jwt
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from a2a_mvp.config import Config
from a2a_mvp.telemetry import configure_tracing
from starlette.testclient import TestClient
from a2a_mvp.server.app import build_app
from tests.stub import make_stub

_OTEL_CFG = Config(otel_enabled=True, otel_service_name="test-agent",
                   jwt_secret="s", jwt_issuer="https://issuer.local",
                   jwt_audience="a2a-mvp", jwt_algorithms=["HS256"])


@pytest.fixture(scope="module")
def exporter():
    exp = InMemorySpanExporter()
    configure_tracing(_OTEL_CFG, span_exporter=exp)
    return exp


@pytest.fixture(scope="module", autouse=True)
def _uninstrument_httpx_after_module():
    yield
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().uninstrument()
    except Exception:
        pass


def _token():
    return jwt.encode({"sub": "peer", "iss": _OTEL_CFG.jwt_issuer,
                       "aud": _OTEL_CFG.jwt_audience, "exp": int(time.time()) + 60},
                      _OTEL_CFG.jwt_secret, algorithm="HS256")


def test_configure_disabled_returns_none():
    assert configure_tracing(Config()) is None


def test_manual_span_exported(exporter):
    exporter.clear()
    tracer = trace.get_tracer("t")
    with tracer.start_as_current_span("manual"):
        pass
    assert "manual" in [s.name for s in exporter.get_finished_spans()]


def test_inbound_request_produces_server_span(exporter):
    exporter.clear()
    app = build_app(_OTEL_CFG, model=make_stub("otel reply"))
    client = TestClient(app)
    r = client.get("/.well-known/agent-card.json")
    assert r.status_code == 200
    kinds = [str(s.kind) for s in exporter.get_finished_spans()]
    assert any("SERVER" in k for k in kinds)


def test_authenticated_rpc_produces_dispatch_spans(exporter):
    exporter.clear()
    app = build_app(_OTEL_CFG, model=make_stub("otel reply"))
    client = TestClient(app)
    body = {
        "jsonrpc": "2.0", "id": "1", "method": "message/send",
        "params": {"message": {"role": "user",
                               "parts": [{"kind": "text", "text": "hi"}],
                               "messageId": "m1"}},
    }
    r = client.post("/", json=body, headers={"Authorization": f"Bearer {_token()}"})
    assert r.status_code == 200

    spans = exporter.get_finished_spans()
    assert len(spans) >= 2, [(s.name, str(s.kind)) for s in spans]
    assert any(str(s.kind).endswith("INTERNAL") for s in spans), \
        [(s.name, str(s.kind)) for s in spans]


def test_disabled_config_serves_card_without_instrumentation_error():
    cfg = Config(otel_enabled=False, jwt_secret="s", jwt_issuer="https://issuer.local",
                 jwt_audience="a2a-mvp", jwt_algorithms=["HS256"])
    app = build_app(cfg, model=make_stub("x"))
    client = TestClient(app)
    r = client.get("/.well-known/agent-card.json")
    assert r.status_code == 200
