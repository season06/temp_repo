"""sync↔async 橋:MCP tool 是 async-only,同步 API 一律經由此模組跑 async 路徑。"""

import asyncio
from concurrent.futures import ThreadPoolExecutor


def run_sync(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
