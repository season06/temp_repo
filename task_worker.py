import asyncio
from abc import ABC, abstractmethod
import random

class TaskWorker(ABC):
    """
    Abstract base class for all task workers
    """
    def __init__(self, poll_interval=3):
        self.poll_interval = poll_interval

    async def batch_poll(self):
        # 模擬從 conductor 拉 tasks
        await asyncio.sleep(0.1)
        return [{"id": f"{self.__class__.__name__}_{i}", "duration": random.randint(1, 10)} for i in range(3)]

    async def start_with_timeout(self, task, timeout=10):
        """
        Execute a task with timeout protection
        """
        try:
            await asyncio.wait_for(self.execute(task), timeout=timeout)
        except asyncio.TimeoutError:
            print(f"[Task {task['id']}] Timeout after {timeout}s")

    async def worker_loop(self, task_name):
        """
        Worker main coroutine loop
        """
        while True:
            try:
                tasks = await self.batch_poll()
                await asyncio.gather(*[self.start_with_timeout(task) for task in tasks])
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                print(f"Worker loop exception in {task_name}:", e)

    @abstractmethod
    async def execute(self, task):
        raise 
