from a2a.server.agent_execution import AgentExecutor
from a2a.utils import new_agent_text_message, get_message_text
from a2a_mvp.server.auth import current_principal


class DeepAgentExecutor(AgentExecutor):
    def __init__(self, agent):
        self.agent = agent

    async def execute(self, context, event_queue):
        query = _extract_text(context)
        principal = current_principal()
        config = {"configurable": {"principal_sub": principal.subject if principal else None}}
        result = await self.agent.ainvoke(
            {"messages": [{"role": "user", "content": query}]}, config=config
        )
        text = result["messages"][-1].content
        await event_queue.enqueue_event(new_agent_text_message(text))

    async def cancel(self, context, event_queue):
        raise NotImplementedError("cancel not supported in MVP")


def _extract_text(context):
    msg = getattr(context, "message", None)
    if msg is None:
        return ""
    try:
        return get_message_text(msg)
    except Exception:
        return str(msg)
