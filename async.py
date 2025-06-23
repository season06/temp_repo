import aiohttp
import asyncio
import time
import requests

async def task_1():
    print("Task 1 started")
    await asyncio.sleep(2)  # Simulate a 2-second task
    print("Task 1 completed")

async def task_2():
    print("Task 2 started")
    await asyncio.sleep(2)  # Simulate a 1-second task
    print("Task 2 completed")

async def main_template():
    await asyncio.gather(task_1(), task_2())  # Run both tasks concurrently

# ====== 包裝同步邏輯，使其 awatable ======

def task_1_time():
    print("Task 1 started")
    time.sleep(2)  # Simulate a 2-second task
    print("Task 1 completed")

def task_2_time():
    print("Task 2 started")
    time.sleep(2)  # Simulate a 1-second task
    print("Task 2 completed")

async def main_template_time():
    await asyncio.gather(
        asyncio.to_thread(task_1_time),
        asyncio.to_thread(task_2_time)
    )  # Run both tasks concurrently

# ====== sync vs async ======

# === 異步 ===

async def fetch(session, url):
    async with session.get(url) as resp:
        return await resp.text()

async def main_async():
    urls = ["https://jsonplaceholder.typicode.com/todos/1"] * 100
    async with aiohttp.ClientSession() as session:
        tasks = [fetch(session, url) for url in urls]
        results = await asyncio.gather(*tasks)
        return results

# === 同步 ===

def main_sync():
    urls = ["https://jsonplaceholder.typicode.com/todos/1"] * 100
    results = []
    for url in urls:
        resp = requests.get(url)
        results.append(resp.text)
    return results


if __name__ == "__main__":
    start_time = time.time()

    # asyncio.run(main_template())
    asyncio.run(main_template_time())

    # asyncio.run(main_async())
    # main_sync()
    print(f"Total time taken: {time.time() - start_time} seconds")

    from concurrent.futures import ThreadPoolExecutor
