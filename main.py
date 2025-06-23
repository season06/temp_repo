import asyncio
import multiprocessing as mp
import signal
import time
# import redis
import json
import psutil

from tasks import *

"""
main.py                        → 啟動 WorkerManager
├── WorkerManager              → 管理多個 Process，按 task name 建立對應的 worker
├── TaskWorker (Base)          → 每個 task 類別繼承此 class
│   ├── start_with_timeout() → 每個任務的執行邏輯進入點
│   └── worker_loop()          → 協程主邏輯
├── LogToDBTask                → 特定任務實作
└── DomainServiceTask          → 特定任務實作
"""

# === REDIS CONFIG SYNC ===
REDIS_KEY = "conductor_worker_config"
# redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)

# === DEFAULT CONFIG ===
CONFIG = {
    'tasks': ['log_to_db', 'domain_service'],
    'loading': 'low',
    'task_setting': {
        'log_to_db': {
            'low': {'process_count': 2, 'poll_interval': 8},
            'mid': {'process_count': 3, 'poll_interval': 8},
            'high': {'process_count': 4, 'poll_interval': 8},
        },
        'domain_service': {
            'low': {'process_count': 2, 'poll_interval': 8},
            'mid': {'process_count': 3, 'poll_interval': 8},
            'high': {'process_count': 4, 'poll_interval': 8},
        }
    }
}

def get_task_class(task_name):
    """
    Map task name strings to their corresponding classes
    """
    mapping = {
        "log_to_db": LogToDB,
        "domain_service": DomainService,
    }
    return mapping.get(task_name)

def worker_entry(task_name: str, poll_interval: int):
    """
    Entry point for a single worker process
    """
    task_cls = get_task_class(task_name)
    if not task_cls:
        print(f"Unknown task: {task_name}")
        return
    print(f"Starting {task_name} worker (poll every {poll_interval}s)")
    worker = task_cls(poll_interval=poll_interval)
    asyncio.run(worker.worker_loop(task_name))


class WorkerManager:
    """
    Manage process count for each task worker
    Args:
        processes (dict): Track all running processes per task
        current_config (dict): Worker config for process count from Redis
    """
    def __init__(self):
        self.processes = {}  # { task_name: [proc1, proc2, ...] }
        self.current_config = {}

    def sync_config_from_redis(self):
        try:
            config_data = CONFIG  # redis_client.get(REDIS_KEY)
            return config_data
        except Exception as e:
            print("[WorkerManager] Failed to sync config from Redis:", e)

    def _start_worker(self, task_name, poll_interval):
        proc = mp.Process(target=worker_entry, args=(task_name, poll_interval))
        proc.start()
        return proc

    def sync_processes(self, config: dict):
        """
        Sync current processes based on the new config
        """
        if config == self.current_config:
            return  # No change in config, skip

        print("[WorkerManager] Config changed, syncing workers...")
        self.current_config = config

        tasks = config.get("tasks", [])
        loading = config.get("loading", "low")
        task_setting = config.get("task_setting", {})

        for task_name in tasks:
            setting = task_setting.get(task_name, {}).get(loading, {})
            desired_count = setting.get("process_count", 1)
            poll_interval = setting.get("poll_interval", 3)
                
            current_list = self.processes.get(task_name, [])
            current_count = len(current_list)

            # Scale up
            if desired_count > current_count:
                for _ in range(desired_count - current_count):
                    proc = self._start_worker(task_name, poll_interval)
                    current_list.append(proc)
            # Scale down
            elif desired_count < current_count:
                for p in current_list[:current_count - desired_count]:
                    p.terminate()
                    current_list.remove(p)

            self.processes[task_name] = current_list
        print(self.processes)

    def _is_zombie(self, proc):
        try:
            p = psutil.Process(proc.pid)
            return p.status() == psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False

    def check_health(self):
        """
        Restart any dead worker processes
        """
        for task_name, proc_list in self.processes.items():
            for idx, proc in enumerate(proc_list):
                if not proc.is_alive() or self._is_zombie(proc):
                    print(f"[WorkerManager] Restarting dead/zombie worker for task {task_name}")
                    try:
                        proc.join(timeout=1)  # clean up zombie if needed
                    except Exception:
                        pass
                    poll_interval = self._get_poll_interval(task_name)
                    new_proc = self._start_worker(task_name, poll_interval)
                    self.processes[task_name][idx] = new_proc

    def _get_poll_interval(self, task_name):
        loading = self.current_config.get("loading", "low")
        return self.current_config.get("task_setting", {}).get(task_name, {}).get(loading, {}).get("poll_interval", 3)

    def shutdown(self):
        for procs in self.processes.values():
            for proc in procs:
                proc.terminate()
        self.processes.clear()

def main():
    manager = WorkerManager()
    try:
        while True:
            config = manager.sync_config_from_redis()
            if config:
                manager.sync_processes(config)
                manager.check_health()
            time.sleep(5)
    except KeyboardInterrupt:
        print("[Main] Shutting down")
        manager.shutdown()


if __name__ == "__main__":
    main()

"""
ref:
https://www.maxlist.xyz/2020/03/20/multi-processing-pool/
https://jimmy-huang.medium.com/python-asyncio-%E5%8D%94%E7%A8%8B-%E4%BA%8C-e717018bb984
"""