import time
import pytest
import os
import psutil
import multiprocessing as mp

from main import WorkerManager, CONFIG

# Override CONFIG with fixed test data
TEST_CONFIG = {
    'tasks': ['log_to_db'],
    'loading': 'low',
    'task_setting': {
        'log_to_db': {
            'low': {'process_count': 1, 'poll_interval': 2},
        }
    }
}

def crash_worker():
    print(f"[{os.getpid()}] crashing intentionally")
    os._exit(1)  # simulate crash (no cleanup)

@pytest.fixture
def manager():
    mgr = WorkerManager()
    yield mgr
    mgr.shutdown()

def test_worker_restarts_after_crash(manager):
    # Sync initial config
    manager.sync_processes(TEST_CONFIG)
    
    # Assert: 1 process running
    assert 'log_to_db' in manager.processes
    procs = manager.processes['log_to_db']
    assert len(procs) == 1
    proc = procs[0]
    assert proc.is_alive()

    # Simulate crash
    proc.terminate()
    proc.join(timeout=2)
    assert not proc.is_alive()

    # Call health check (should restart the worker)
    manager.check_health()
    new_proc = manager.processes['log_to_db'][0]

    # Assert: new process is running, and not same as old
    assert new_proc.is_alive()
    assert new_proc.pid != proc.pid

def test_zombie_process_detection_and_replacement(manager):
    # Replace normal worker with crashing one
    proc = mp.Process(target=crash_worker)
    proc.start()
    task_name = 'log_to_db'
    manager.processes[task_name] = [proc]

    time.sleep(1)  # let it crash

    # Confirm process has exited but is still a zombie (depends on OS)
    try:
        p = psutil.Process(proc.pid)
        assert p.status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        pytest.skip("Zombie process already reaped by OS")

    # Call health check
    manager.current_config = TEST_CONFIG  # manually set config to avoid sync
    manager.check_health()

    # Confirm new process is created
    new_proc = manager.processes[task_name][0]
    assert new_proc.pid != proc.pid
    assert new_proc.is_alive()