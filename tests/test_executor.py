import asyncio
from types import SimpleNamespace
from a2a_mvp.config import Config
from a2a_mvp.agent import build_agent
from a2a_mvp.server.executor import DeepAgentExecutor
from tests.stub import make_stub


class FakeQueue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, event):
        self.events.append(event)


def test_execute_emits_agent_text():
    agent = build_agent(Config(), model=make_stub("bridged reply"))
    ex = DeepAgentExecutor(agent)
    ctx = SimpleNamespace(message="說個回應", current_task=None)
    q = FakeQueue()
    asyncio.run(ex.execute(ctx, q))
    dumped = str(q.events)
    assert "bridged reply" in dumped
