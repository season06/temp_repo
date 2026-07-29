"""Agent registry:以 agent.name 撈遠端 agent 定義(zip),任何失敗 fallback local。"""

import io
import logging
import os
import shutil
import warnings
import zipfile
from pathlib import Path

import httpx
import yaml
from pydantic import BaseModel, ConfigDict

from ..config import AgentSection, McpServer

logger = logging.getLogger("agent_template")


class RemoteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent: AgentSection = AgentSection()
    mcp: list[McpServer] = []
    skills: object = None  # 接受但忽略:skill 以 zip 內 skills/ 目錄為準


class RemoteBundle:
    def __init__(self, config, skills_dir):
        self.config = config
        self.skills_dir = skills_dir


def fetch_remote(agent_name):
    url = os.environ.get("AGENT_REGISTRY_URL", "").strip()
    if not url or not agent_name:
        return None
    endpoint = f"{url.rstrip('/')}/agents/{agent_name}"
    try:
        response = httpx.get(endpoint, timeout=10)
    except Exception as exc:
        warnings.warn(f"agent registry 連線失敗,使用 local 設定: {exc}")
        return None
    if response.status_code == 404:
        logger.info("registry 查無 agent '%s',使用 local 設定", agent_name)
        return None
    if response.status_code != 200:
        warnings.warn(f"agent registry 回應 {response.status_code},使用 local 設定")
        return None
    try:
        return _extract(agent_name, response.content)
    except Exception as exc:
        warnings.warn(f"registry 資料無法解析,使用 local 設定: {exc}")
        return None


def remote_mcp_headers():
    token = os.environ.get("AUTH_TOKEN", "").strip()
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}


def _extract(agent_name, zip_bytes):
    target = _cache_root() / agent_name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for member in zf.namelist():
            dest = (target / member).resolve()
            if not dest.is_relative_to(target.resolve()):
                raise ValueError(f"zip 內含非法路徑: {member}")
        zf.extractall(target)
    raw = yaml.safe_load((target / "config.yaml").read_text(encoding="utf-8")) or {}
    config = RemoteConfig.model_validate(raw)
    skills_dir = target / "skills"
    logger.info("registry 取得 agent '%s' 定義", agent_name)
    return RemoteBundle(config, str(skills_dir) if skills_dir.is_dir() else None)


def _cache_root():
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "agent_template"
