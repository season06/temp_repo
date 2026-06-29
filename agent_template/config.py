from __future__ import annotations

from dataclasses import dataclass

from .errors import ConfigError


@dataclass(frozen=True)
class AgentConfig:
    model: str
    base_url: str
    api_key: str
    temperature: float = 0.0
    max_tokens: int | None = None
    timeout: float = 60.0
    max_retries: int = 2
    enable_audit_log: bool = True

    def __post_init__(self) -> None:
        if not self.model:
            raise ConfigError("model 不可為空")
        if not self.base_url:
            raise ConfigError("base_url 不可為空")
        if not self.api_key:
            raise ConfigError("api_key 不可為空")
        if self.temperature < 0:
            raise ConfigError("temperature 不可為負")
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise ConfigError("max_tokens 須為正整數或 None")
        if self.timeout <= 0:
            raise ConfigError("timeout 須為正數")
        if self.max_retries < 0:
            raise ConfigError("max_retries 不可為負")
