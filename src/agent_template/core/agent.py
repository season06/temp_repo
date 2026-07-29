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
    def __init__(self, native):
        self.native = native

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
