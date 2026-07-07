from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.utils import AGENT_CARD_WELL_KNOWN_PATH
from a2a_mvp.agent import build_agent
from a2a_mvp.server.executor import DeepAgentExecutor
from a2a_mvp.server.card import build_agent_card
from a2a_mvp.server.auth import AuthMiddleware


def build_app(config, model=None):
    agent = build_agent(config, model=model)
    card = build_agent_card(config)
    handler = DefaultRequestHandler(
        agent_executor=DeepAgentExecutor(agent),
        task_store=InMemoryTaskStore(),
    )
    app = A2AStarletteApplication(agent_card=card, http_handler=handler).build()
    app.add_middleware(AuthMiddleware, config=config,
                       exempt_paths=[AGENT_CARD_WELL_KNOWN_PATH])
    return app
