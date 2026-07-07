import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "not-needed"
    llm_model: str = "qwen2.5"
    jwt_issuer: str = "https://issuer.local"
    jwt_audience: str = "a2a-mvp"
    jwt_algorithms: list = field(default_factory=lambda: ["HS256"])
    jwt_secret: str = ""          # HS256 用;RS256 時改用 jwt_jwks_url / jwt_public_key
    jwt_jwks_url: str = ""
    jwt_public_key: str = ""
    host: str = "127.0.0.1"
    port: int = 9999
    public_url: str = "http://127.0.0.1:9999"
    allowed_remote_agents: list = field(default_factory=list)
    outbound_service_token: str = ""   # 出站呼叫 peer 帶的服務憑證

    @classmethod
    def from_env(cls):
        algos = os.environ.get("A2A_JWT_ALGORITHMS", "HS256")
        remotes = os.environ.get("A2A_ALLOWED_REMOTE_AGENTS", "")
        return cls(
            llm_base_url=os.environ.get("A2A_LLM_BASE_URL", cls.llm_base_url),
            llm_api_key=os.environ.get("A2A_LLM_API_KEY", cls.llm_api_key),
            llm_model=os.environ.get("A2A_LLM_MODEL", cls.llm_model),
            jwt_issuer=os.environ.get("A2A_JWT_ISSUER", cls.jwt_issuer),
            jwt_audience=os.environ.get("A2A_JWT_AUDIENCE", cls.jwt_audience),
            jwt_algorithms=[a.strip() for a in algos.split(",") if a.strip()],
            jwt_secret=os.environ.get("A2A_JWT_SECRET", ""),
            jwt_jwks_url=os.environ.get("A2A_JWT_JWKS_URL", ""),
            jwt_public_key=os.environ.get("A2A_JWT_PUBLIC_KEY", ""),
            host=os.environ.get("A2A_HOST", cls.host),
            port=int(os.environ.get("A2A_PORT", cls.port)),
            public_url=os.environ.get("A2A_PUBLIC_URL", cls.public_url),
            allowed_remote_agents=[r.strip() for r in remotes.split(",") if r.strip()],
            outbound_service_token=os.environ.get("A2A_OUTBOUND_SERVICE_TOKEN", ""),
        )
