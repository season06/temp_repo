"""AgentA2AExecutor:把薄包裝 Agent 接上 A2A,以 astream 推事件。

一套實作同時服務 message/send(handler 聚合到終態)與 message/stream(逐事件收)。
auth 為殼:async callable 回 False → 回 "unauthorized";等 auth spec 定案填肉。
"""

from a2a.helpers.proto_helpers import get_message_text, new_task, new_text_part
from a2a.server.agent_execution import AgentExecutor
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState


class AgentA2AExecutor(AgentExecutor):
    def __init__(self, agent, auth=None):
        self._agent = agent
        self._auth = auth

    async def execute(self, context, event_queue):
        if context.current_task is None:
            # handler 要先收到 Task 物件本身,之後才能推狀態更新事件
            await event_queue.enqueue_event(
                new_task(context.task_id, context.context_id, TaskState.TASK_STATE_SUBMITTED)
            )
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        if self._auth is not None and not await self._auth(context):
            await updater.reject(
                updater.new_agent_message([new_text_part("unauthorized")])
            )
            return
        await updater.start_work()
        text = get_message_text(context.message)
        parts = []
        try:
            async for chunk in self._agent.astream(text):
                parts.append(chunk)
                await updater.update_status(
                    TaskState.TASK_STATE_WORKING,
                    message=updater.new_agent_message([new_text_part(chunk)]),
                )
        except Exception as exc:
            await updater.failed(updater.new_agent_message([new_text_part(str(exc))]))
            return
        await updater.add_artifact([new_text_part("".join(parts))], name="answer")
        await updater.complete()

    async def cancel(self, context, event_queue):
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()
