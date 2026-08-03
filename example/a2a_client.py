"""呼叫遠端 A2A agent 的範例(串流):先在另一個終端跑 serve.py,再執行本檔。"""

import asyncio

from agent_template.loaders.a2a import stream_a2a


async def main():
    async for chunk in stream_a2a("http://localhost:9000", "what time is it"):
        print(chunk, end="", flush=True)
    print()


asyncio.run(main())
