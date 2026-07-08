import httpx

from .hooks import Hook, StopRound


class AuthClient:
    """auth 檢查介面;verify 回傳 True=放行。正式契約由團隊定,MVP 用 HttpAuthClient 或測試注入 fake。"""

    def verify(self, context):
        raise NotImplementedError


class HttpAuthClient(AuthClient):
    """打一個 HTTP request 到 auth 端點;HTTP 200 代表放行（MVP mock）。
    連線/HTTP 錯誤一律視為未通過（fail-closed）。"""

    def __init__(self, endpoint, timeout=5.0):
        self._endpoint = endpoint
        self._timeout = timeout

    def verify(self, context):
        try:
            response = httpx.post(self._endpoint, json={"tool": context.tool_name}, timeout=self._timeout)
        except httpx.HTTPError:
            return False
        return response.status_code == 200


class AuthHook(Hook):
    """在 tool 執行前打 auth;未通過則中止該輪（StopRound）。
    MVP 限制:verify 是同步 HTTP;當 agent 以 ainvoke 執行時會短暫阻塞 event loop。"""

    def __init__(self, client):
        self._client = client

    def before_tool(self, context):
        if self._client.verify(context):
            return None
        return StopRound(reason="auth denied for tool: " + str(context.tool_name))
