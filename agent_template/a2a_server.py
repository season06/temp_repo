from starlette.applications import Starlette

from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.helpers.proto_helpers import new_text_message
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from a2a.utils.constants import DEFAULT_RPC_URL


def build_agent_card(name, url, version="0.1.0", description="", skills=None, streaming=True):
    if skills is None:
        skills = [AgentSkill(id="chat", name="Chat", description="Converse with the agent.", tags=["chat"])]
    return AgentCard(
        name=name,
        description=description,
        version=version,
        capabilities=AgentCapabilities(streaming=streaming),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=skills,
        supported_interfaces=[AgentInterface(url=url, protocol_binding="JSONRPC", protocol_version="1.0")],
    )


class AgentA2AExecutor(AgentExecutor):
    """把本 SDK 的原生 agent 接上 A2A。入站可選 async auth;通過後跑 agent.ainvoke,回最終文字。"""

    def __init__(self, agent, auth_client=None):
        self._agent = agent
        self._auth_client = auth_client

    async def execute(self, context, event_queue):
        if self._auth_client is not None and not await self._auth_client.verify(context):
            await event_queue.enqueue_event(
                new_text_message(text="unauthorized", context_id=context.context_id, task_id=context.task_id)
            )
            return
        user_text = context.get_user_input()
        result = await self._agent.ainvoke({"messages": [("user", user_text)]})
        reply_text = str(result["messages"][-1].content)
        await event_queue.enqueue_event(
            new_text_message(text=reply_text, context_id=context.context_id, task_id=context.task_id)
        )

    async def cancel(self, context, event_queue):
        return None


def build_a2a_app(agent, card, auth_client=None):
    handler = DefaultRequestHandler(
        agent_executor=AgentA2AExecutor(agent, auth_client=auth_client),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    routes = create_agent_card_routes(card) + create_jsonrpc_routes(handler, rpc_url=DEFAULT_RPC_URL)
    return Starlette(routes=routes)
