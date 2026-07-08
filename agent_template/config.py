from __future__ import annotations

import os


class AgentConfig:
    """單一 agent 的 LLM 設定（OpenAI-compatible 端點）。"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float = 0.0,
        system_prompt: str | None = None,
    ) -> None:
        self.api_key: str = api_key
        self.base_url: str = base_url
        self.model: str = model
        self.temperature: float = temperature
        self.system_prompt: str | None = system_prompt


class Config:
    """SDK runtime 設定：auth 端點與 Observability。"""

    def __init__(
        self,
        auth_endpoint: str | None = None,
        otel_endpoint: str | None = None,
        sampling_ratio: float = 1.0,
        o11y_enabled: bool = True,
        cid: str | None = None,
        agent_version: str | None = None,
        service_name: str = "agent_template",
    ) -> None:
        self.auth_endpoint: str | None = auth_endpoint
        self.otel_endpoint: str | None = otel_endpoint
        self.sampling_ratio: float = sampling_ratio
        self.o11y_enabled: bool = o11y_enabled
        self.cid: str | None = cid
        self.agent_version: str | None = agent_version
        self.service_name: str = service_name

    @classmethod
    def from_env(cls) -> Config:
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
