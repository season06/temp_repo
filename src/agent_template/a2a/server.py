"""A2A server 殼:CardSpec → AgentCard、組 routes、build ASGI app。"""

from starlette.applications import Starlette

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from a2a.utils.constants import DEFAULT_RPC_URL

from .executor import AgentA2AExecutor

_DEFAULT_SKILL = AgentSkill(
    id="chat", name="Chat", description="Converse with the agent.", tags=["chat"]
)


def build_agent_card(spec, host, port):
    url = spec.url or f"http://{host}:{port}"
    skills = [
        AgentSkill(id=s.id, name=s.name, description=s.description, tags=list(s.tags))
        for s in spec.skills
    ] or [_DEFAULT_SKILL]
    return AgentCard(
        name=spec.name,
        description=spec.description,
        version=spec.version,
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=skills,
        supported_interfaces=[
            AgentInterface(url=url, protocol_binding="JSONRPC", protocol_version="1.0")
        ],
    )


def build_a2a_app(agent, spec, host="0.0.0.0", port=9000, auth=None):
    card = build_agent_card(spec, host, port)
    handler = DefaultRequestHandler(
        agent_executor=AgentA2AExecutor(agent, auth=auth),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    routes = [
        *create_agent_card_routes(card),
        *create_jsonrpc_routes(handler, DEFAULT_RPC_URL),
    ]
    return Starlette(routes=routes)
