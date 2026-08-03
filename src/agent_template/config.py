"""Config 載入:yaml + .env,fail-fast 驗證,人話錯誤訊息。"""

import difflib
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, ValidationError


class ConfigError(Exception):
    """config 檔錯誤,訊息直接給使用者看。"""


class AgentSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = ""  # agent registry 的查詢 key(暫定,等團隊定案 id 規格)
    provider: str = "deepagent"
    model: str = ""
    system_prompt: str = ""


class McpServer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    transport: str = "streamable-http"
    url: str


class A2aAgent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    url: str


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent: AgentSection = AgentSection()
    agent_card: str = ""  # card 檔路徑指標;空值則找 config 同目錄的 agent_card.yaml/.json
    local_mcp: list[McpServer] = []
    local_tools: list[str] = []
    local_skills: list[str] = []
    local_a2a: list[A2aAgent] = []


_ALL_FIELDS = [
    *Config.model_fields,
    *AgentSection.model_fields,
    *McpServer.model_fields,
    *A2aAgent.model_fields,
]


def load_config(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ConfigError(f"找不到 config 檔: {path}")
    load_dotenv(path.parent / ".env", override=False)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    try:
        config = Config.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(_humanize(exc)) from exc
    config.local_tools = [str(path.parent / p) for p in config.local_tools]
    config.local_skills = [str(path.parent / p) for p in config.local_skills]
    config.agent_card = _resolve_card_path(path.parent, config.agent_card)
    return config


def _resolve_card_path(base_dir, declared):
    """card 檔路徑:有宣告就用宣告的;否則找同目錄的 agent_card.yaml / agent_card.json。"""
    if declared:
        return str(base_dir / declared)
    for name in ("agent_card.yaml", "agent_card.json"):
        candidate = base_dir / name
        if candidate.is_file():
            return str(candidate)
    return ""


def _humanize(exc):
    lines = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"])
        if err["type"] == "extra_forbidden":
            guess = difflib.get_close_matches(str(err["loc"][-1]), _ALL_FIELDS, n=1)
            hint = f'(是不是 "{guess[0]}"?)' if guess else ""
            lines.append(f'不認識的欄位 "{loc}" {hint}')
        else:
            lines.append(f'欄位 "{loc}": {err["msg"]}')
    return "config 檔有誤:\n" + "\n".join(f"- {line}" for line in lines)
