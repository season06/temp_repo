"""remote registry resolver:把 config 的 RemoteRef 解析成 LocalMcp / LocalSkill,
匯流回既有的 local 載入路徑。registry 契約尚未定案,見 docs/designs/remote-registry-resolver.md。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from ..config import LocalMcp

if TYPE_CHECKING:
    from ..config import LocalSkill, RemoteRef


class RegistryClient:
    """resolver 介面。registry_url 由 ref 帶入(支援多組 registry),故 client 無狀態。"""

    def resolve_mcps(self, ref: RemoteRef) -> list[LocalMcp]:
        raise NotImplementedError

    def resolve_skills(self, ref: RemoteRef) -> list[LocalSkill]:
        raise NotImplementedError


class HttpRegistryClient(RegistryClient):
    """打 registry HTTP 端點逐 name 解析;任何錯誤 fail-loud(缺宣告的工具該炸)。"""

    def __init__(self, timeout: float = 5.0) -> None:
        self._timeout = timeout

    def resolve_mcps(self, ref: RemoteRef) -> list[LocalMcp]:
        if not ref.registry_url or not ref.name:
            return []
        return [self._fetch_mcp(ref.registry_url, name) for name in ref.name]

    def resolve_skills(self, ref: RemoteRef) -> list[LocalSkill]:
        if not ref.registry_url or not ref.name:
            return []
        raise NotImplementedError(
            "remote skills 未定案;見 docs/designs/remote-registry-resolver.md (D1)"
        )

    def _fetch_mcp(self, registry_url: str, name: str) -> LocalMcp:
        response = httpx.get(f"{registry_url.rstrip('/')}/mcp/{name}", timeout=self._timeout)
        response.raise_for_status()
        data = response.json()
        return LocalMcp(name=name, transport=data["transport"], path=data["url"], func=data.get("func", []))
