from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from .hooks import Hook, StopRound

if TYPE_CHECKING:
    from .hooks import HookContext


class AuthClient:
    """auth 檢查介面;verify 回傳 True=放行。正式契約由團隊定,MVP 用 HttpAuthClient 或測試注入 fake。"""

    def verify(self, context: Any) -> bool:
        raise NotImplementedError


class HttpAuthClient(AuthClient):
    """打一個 HTTP request 到 auth 端點;HTTP 200 代表放行（MVP mock）。
    連線/HTTP 或任何錯誤一律視為未通過（fail-closed）。"""

    def __init__(self, endpoint: str, timeout: float = 5.0) -> None:
        self._endpoint = endpoint
        self._timeout = timeout

    def verify(self, context: Any) -> bool:
        try:
            response = httpx.post(self._endpoint, json={"tool": context.tool_name}, timeout=self._timeout)
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


class AsyncAuthClient:
    """非同步 auth 介面(A2A 入站用);verify 回傳 True=放行。"""

    async def verify(self, context: Any) -> bool:
        raise NotImplementedError


class AsyncHttpAuthClient(AsyncAuthClient):
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
