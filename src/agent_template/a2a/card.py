"""Agent Card 檔解析:獨立 yaml/json 檔,local 解析失敗 fail fast、remote 爛 fallback local。"""

import json
import logging
import warnings
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from ..config import ConfigError

logger = logging.getLogger("agent_template")


class CardSkill(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    description: str = ""
    tags: list[str] = []


class CardSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str = ""
    version: str = "0.1.0"
    url: str = ""
    skills: list[CardSkill] = []


def resolve_card(local_path, remote_path):
    """回傳 CardSpec 或 None(兩邊都沒有)。remote 整檔優先;remote 爛 → warning + fallback local。"""
    if remote_path:
        try:
            card = load_card_file(remote_path)
            logger.info("使用 remote agent card: %s", remote_path)
            return card
        except Exception as exc:
            warnings.warn(f"remote agent card 無法解析,改用 local: {exc}")
    if local_path:
        return load_card_file(local_path)  # local 錯就炸(fail fast,同 config 打錯字)
    return None


def load_card_file(path):
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"找不到 agent card 檔: {path}")
    text = path.read_text(encoding="utf-8")
    raw = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    try:
        return CardSpec.model_validate(raw or {})
    except ValidationError as exc:
        raise ConfigError(f"agent card 檔有誤 ({path}):\n{exc}") from exc
