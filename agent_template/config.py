import os


class AgentConfig:
    """單一 agent 的 LLM 設定（OpenAI-compatible 端點）。"""

    def __init__(self, api_key, base_url, model, temperature=0.0, system_prompt=None):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.system_prompt = system_prompt


class Config:
    """SDK runtime 設定：auth 端點與 Observability。"""

    def __init__(self, auth_endpoint=None, otel_endpoint=None, sampling_ratio=1.0,
                 o11y_enabled=True, cid=None, agent_version=None, service_name="agent_template"):
        self.auth_endpoint = auth_endpoint
        self.otel_endpoint = otel_endpoint
        self.sampling_ratio = sampling_ratio
        self.o11y_enabled = o11y_enabled
        self.cid = cid
        self.agent_version = agent_version
        self.service_name = service_name

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
