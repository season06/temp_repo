from a2a.types import AgentCard, AgentSkill, AgentCapabilities


def build_agent_card(config):
    skill = AgentSkill(
        id="general_assist",
        name="General Assistant",
        description="回答問題,必要時委派給其他 A2A agent。",
        tags=["assistant", "delegation"],
        examples=["幫我查這個並整理成三點"],
    )
    return AgentCard(
        name="A2A MVP DeepAgent",
        description="MVP deepagent:JWT 保護的 A2A server,兼具 client 能力。",
        url=f"{config.public_url}/",
        version="0.1.0",
        defaultInputModes=["text/plain"],
        defaultOutputModes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[skill],
        securitySchemes={
            "bearer": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
        },
        security=[{"bearer": []}],
    )
