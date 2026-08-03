"""Agent 薄包裝:str 進 str 出;dict 透傳原生行為;原生物件掛 .native。

所有路徑內部都走原生 async API —— MCP tool 是 async-only,
原生同步 invoke 會 NotImplementedError,故同步介面只是 async 的橋接。
"""

import asyncio
import queue
import threading

from langchain_core.messages import AIMessageChunk

from ..utils._async import run_sync

_DONE = object()


class Agent:
    def __init__(self, native, card=None):
        self.native = native
        self._card = card  # CardSpec;serve()/a2a_app() 才需要

    def a2a_app(self, host="0.0.0.0", port=9000, auth=None):
        """回傳 A2A 的 ASGI app(掛既有服務、自控部署、測試直打用)。"""
        from ..a2a.server import build_a2a_app
        from ..config import ConfigError

        if self._card is None:
            raise ConfigError(
                "找不到 agent card:請在 config 同目錄建立 agent_card.yaml,"
                "或在 config 以 agent_card: 指定路徑"
            )
        return build_a2a_app(self, self._card, host=host, port=port, auth=auth)

    def serve(self, host="0.0.0.0", port=9000, auth=None):
        """一行把 agent 曝露成 A2A 端點(阻塞執行)。"""
        import uvicorn

        uvicorn.run(self.a2a_app(host=host, port=port, auth=auth), host=host, port=port)

    def invoke(self, message):
        return run_sync(self.ainvoke(message))

    async def ainvoke(self, message):
        if not isinstance(message, str):
            return await self.native.ainvoke(message)
        result = await self.native.ainvoke(_payload(message))
        return result["messages"][-1].content

    async def astream(self, message):
        if not isinstance(message, str):
            async for chunk in self.native.astream(message):
                yield chunk
            return
        async for chunk, _metadata in self.native.astream(
            _payload(message), stream_mode="messages"
        ):
            if isinstance(chunk, AIMessageChunk) and isinstance(chunk.content, str) and chunk.content:
                yield chunk.content

    def stream(self, message):
        q = queue.Queue()

        def worker():
            async def pump():
                async for item in self.astream(message):
                    q.put(item)

            try:
                asyncio.run(pump())
                q.put(_DONE)
            except BaseException as exc:
                q.put(exc)

        threading.Thread(target=worker, daemon=True).start()
        while True:
            item = q.get()
            if item is _DONE:
                return
            if isinstance(item, BaseException):
                raise item
            yield item


def _payload(message):
    return {"messages": [{"role": "user", "content": message}]}
