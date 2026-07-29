import asyncio

from agent_template.utils._async import run_sync


async def double(x):
    return x * 2


def test_run_sync_without_loop():
    assert run_sync(double(21)) == 42


def test_run_sync_inside_running_loop():
    async def main():
        return run_sync(double(21))  # 在 running loop 內呼叫同步橋

    assert asyncio.run(main()) == 42


def test_run_sync_propagates_exception():
    async def boom():
        raise ValueError("kaboom")

    try:
        run_sync(boom())
    except ValueError as exc:
        assert str(exc) == "kaboom"
    else:
        raise AssertionError("should have raised")
