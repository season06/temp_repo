from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

from ..hooks import Hook, StopRound

if TYPE_CHECKING:
    from ..hooks import HookContext


@dataclass
class AuthContext:
    """呼叫端在 invoke/ainvoke 時透過 context= 傳入的身分;middleware 由 runtime.context 讀取。"""

    identity: str | None = None



class HttpAuthClient:
    """打一個 HTTP request 到 auth 端點;HTTP 200 代表放行（MVP mock）。
    連線/HTTP 或任何錯誤一律視為未通過（fail-closed）。"""

    def __init__(self, endpoint: str, timeout: float = 5.0) -> None:
        self._endpoint = endpoint
        self._timeout = timeout

    @staticmethod
    def _auth_payload(context: Any) -> dict:
        """組出要送給 auth 端點的欄位(只放存在的)。
        per-tool 來的 HookContext 帶 tool_name;入口來的 AuthContext 帶 identity。"""
        payload: dict = {}
        tool = getattr(context, "tool_name", None)
        if tool is not None:
            payload["tool"] = tool
        identity = getattr(context, "identity", None)
        if identity is not None:
            payload["identity"] = identity
        return payload

    def verify(self, context: Any) -> bool:
        try:
            response = httpx.post(self._endpoint, json=self._auth_payload(context), timeout=self._timeout)
        except Exception:
            return False
        return response.status_code == 200


class AuthHook(Hook):
    """在 tool 執行前打 auth;未通過則中止該輪（StopRound）。
    MVP 限制:verify 是同步 HTTP;當 agent 以 ainvoke 執行時會短暫阻塞 event loop。"""

    def __init__(self, client: Any) -> None:
        self._client = client

    def before_tool(self, context: HookContext) -> StopRound | None:
        if self._client.verify(context):
            return None
        return StopRound(reason="auth denied for tool: " + str(context.tool_name))


class AsyncHttpAuthClient:
    """非同步版:httpx.AsyncClient 打 auth 端點,200=放行;任何錯誤 fail-closed。
    用於 A2A server 入站邊界(不阻塞 event loop)。"""

    def __init__(self, endpoint: str, timeout: float = 5.0) -> None:
        self._endpoint = endpoint
        self._timeout = timeout

    async def verify(self, context: Any) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self._endpoint, json={"source": "a2a"}, timeout=self._timeout)
        except Exception:
            return False
        return response.status_code == 200
