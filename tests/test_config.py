import os
from a2a_mvp.config import Config


def test_from_env_reads_all_fields(monkeypatch):
    monkeypatch.setenv("A2A_LLM_BASE_URL", "http://llm.local/v1")
    monkeypatch.setenv("A2A_LLM_API_KEY", "sk-x")
    monkeypatch.setenv("A2A_LLM_MODEL", "qwen-max")
    monkeypatch.setenv("A2A_JWT_ISSUER", "https://issuer")
    monkeypatch.setenv("A2A_JWT_AUDIENCE", "a2a-mvp")
    monkeypatch.setenv("A2A_JWT_ALGORITHMS", "HS256")
    monkeypatch.setenv("A2A_JWT_SECRET", "topsecret")
    monkeypatch.setenv("A2A_ALLOWED_REMOTE_AGENTS", "http://peer.local,http://peer2.local")
    cfg = Config.from_env()
    assert cfg.llm_model == "qwen-max"
    assert cfg.jwt_audience == "a2a-mvp"
    assert cfg.jwt_algorithms == ["HS256"]
    assert "http://peer.local" in cfg.allowed_remote_agents


def test_defaults_when_optional_missing(monkeypatch):
    for k in list(os.environ):
        if k.startswith("A2A_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("A2A_JWT_SECRET", "s")
    cfg = Config.from_env()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 9999
    assert cfg.jwt_algorithms == ["HS256"]


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
