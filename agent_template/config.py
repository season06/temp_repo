"""設定層:每個來源 section 對應一個 pydantic model。

資料來源分兩類:
- `.env`(secrets / 端點):LLM 憑證、Observability、Auth  → `load_from_env`
- `config.yaml`(結構):agent、skills、mcps               → `load_from_yaml`

頂層 `Config` 組合所有 section,並提供 `load` / `load_from_env` / `load_from_yaml`。
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, Field

_TRUTHY = ("true", "1", "yes", "on")


def _read_env(path: str | os.PathLike) -> dict:
    """用 python-dotenv 解析 .env 檔,再疊上真實環境變數(os.environ 優先)。

    dotenv_values 不會改動 os.environ(不像 load_dotenv),避免載入設定時污染全域環境。
    檔案不存在時 dotenv_values 回傳空 dict,故最終只用環境變數。
    """
    values: dict = {k: v for k, v in dotenv_values(path).items() if v is not None}
    values.update(os.environ)
    return values


def _read_yaml(path: str | os.PathLike) -> dict:
    """讀取 yaml 檔為 dict;檔案不存在或為空則回傳 {}。"""
    p = Path(path)
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


# ---------------------------------------------------------------------------
# env-sourced sections (.env)
# ---------------------------------------------------------------------------


class LLMConfig(BaseModel):
    """OpenAI-compatible LLM 端點設定(來源:.env)。"""

    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.0

    @classmethod
    def load_from_env(cls, env: dict) -> LLMConfig:
        temp = env.get("LLM_TEMPERATURE")
        return cls(
            api_key=env.get("LLM_API_KEY", ""),
            base_url=env.get("LLM_BASE_URL", ""),
            model=env.get("LLM_MODEL", ""),
            temperature=float(temp) if temp else 0.0,
        )


class ObservabilityConfig(BaseModel):
    """OpenTelemetry / 監控設定(來源:.env)。"""

    enabled: bool = False
    endpoint: str | None = None
    sampling_ratio: float = 1.0
    service_name: str = "agent_template"
    cid: str | None = None
    agent_version: str | None = None

    @classmethod
    def load_from_env(cls, env: dict) -> ObservabilityConfig:
        enabled = env.get("OTEL_ENABLED")
        ratio = env.get("OTEL_SAMPLING_RATIO")
        return cls(
            enabled=(enabled.strip().lower() in _TRUTHY) if enabled is not None else False,
            endpoint=env.get("OTEL_ENDPOINT"),
            sampling_ratio=float(ratio) if ratio else 1.0,
            service_name=env.get("SERVICE_NAME", "agent_template"),
            cid=env.get("CID"),
            agent_version=env.get("AGENT_VERSION"),
        )


class AuthConfig(BaseModel):
    """入站 / 工具 auth 端點(來源:.env)。"""

    endpoint: str | None = None

    @classmethod
    def load_from_env(cls, env: dict) -> AuthConfig:
        return cls(endpoint=env.get("AUTH_ENDPOINT"))


# ---------------------------------------------------------------------------
# yaml-sourced sections (config.yaml)
# ---------------------------------------------------------------------------


class AgentSettings(BaseModel):
    """agent 區塊:框架 provider 與 system prompt(來源:config.yaml `agent`)。"""

    provider: str = "deepagent"
    system_prompt: str | None = None

    @classmethod
    def load_from_yaml(cls, data: dict) -> AgentSettings:
        agent = data.get("agent") or {}
        return cls(
            provider=agent.get("provider", "deepagent"),
            system_prompt=agent.get("system_prompt"),
        )


class LocalSkill(BaseModel):
    """本地 skill 宣告:name + 指向一個 @tool python 檔的 path。"""

    name: str
    path: str


class RemoteRef(BaseModel):
    """遠端 registry 參照(skills/mcps 共用):registry_url + 名稱清單。MVP 尚未接。"""

    registry_url: str = ""
    name: list[str] = Field(default_factory=list)


class SkillsConfig(BaseModel):
    """skills 區塊:local 檔案清單 + remote registry(來源:config.yaml `skills__*`)。"""

    local: list[LocalSkill] = Field(default_factory=list)
    remote: RemoteRef = Field(default_factory=RemoteRef)

    @classmethod
    def load_from_yaml(cls, data: dict) -> SkillsConfig:
        local = [LocalSkill(**s) for s in (data.get("skills__local") or [])]
        remote = RemoteRef(**(data.get("skills__remote") or {}))
        return cls(local=local, remote=remote)


class LocalMcp(BaseModel):
    """本地 MCP server 宣告:name、transport(stdio / streamable_http)、path、func 篩選清單。"""

    name: str
    transport: str
    path: str
    func: list[str] = Field(default_factory=list)


class McpsConfig(BaseModel):
    """mcps 區塊:local server 清單 + remote registry(來源:config.yaml `mcps__*`)。"""

    local: list[LocalMcp] = Field(default_factory=list)
    remote: RemoteRef = Field(default_factory=RemoteRef)

    @classmethod
    def load_from_yaml(cls, data: dict) -> McpsConfig:
        local = [LocalMcp(**m) for m in (data.get("mcps__local") or [])]
        remote = RemoteRef(**(data.get("mcps__remote") or {}))
        return cls(local=local, remote=remote)


# ---------------------------------------------------------------------------
# top-level composed config
# ---------------------------------------------------------------------------


class Config(BaseModel):
    """組合所有 section 的頂層設定。用 `Config.load(yaml_path, env_path)` 一次載入。"""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    mcps: McpsConfig = Field(default_factory=McpsConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)

    @classmethod
    def load_from_env(cls, path: str | os.PathLike = ".env") -> Config:
        """只從 .env 載入 env-sourced sections(llm / observability / auth);其餘用預設。"""
        env = _read_env(path)
        return cls(
            llm=LLMConfig.load_from_env(env),
            observability=ObservabilityConfig.load_from_env(env),
            auth=AuthConfig.load_from_env(env),
        )

    @classmethod
    def load_from_yaml(cls, path: str | os.PathLike = "config.yaml") -> Config:
        """只從 config.yaml 載入 yaml-sourced sections(agent / skills / mcps);其餘用預設。"""
        data = _read_yaml(path)
        return cls(
            agent=AgentSettings.load_from_yaml(data),
            skills=SkillsConfig.load_from_yaml(data),
            mcps=McpsConfig.load_from_yaml(data),
        )

    @classmethod
    def load(cls, yaml_path: str | os.PathLike = "config.yaml", env_path: str | os.PathLike = ".env") -> Config:
        """完整載入:合併 config.yaml(結構)與 .env(secrets/端點)。"""
        data = _read_yaml(yaml_path)
        env = _read_env(env_path)
        return cls(
            llm=LLMConfig.load_from_env(env),
            agent=AgentSettings.load_from_yaml(data),
            skills=SkillsConfig.load_from_yaml(data),
            mcps=McpsConfig.load_from_yaml(data),
            observability=ObservabilityConfig.load_from_env(env),
            auth=AuthConfig.load_from_env(env),
        )
