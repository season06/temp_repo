import asyncio
import os
from task_worker import TaskWorker

class LogToDB(TaskWorker):
    async def execute(self, task):
        print(f"[{os.getpid()}][{task['id']}] Start for {task['duration']}s")
        await asyncio.sleep(task['duration'])
        print(f"[{os.getpid()}][{task['id']}] DONE")

class DomainService(TaskWorker):
    async def execute(self, task):
        print(f"[{os.getpid()}][{task['id']}] Executing: {task['duration']}s")
        await asyncio.sleep(1.5)
        print(f"[{os.getpid()}][{task['id']}] DONE")