from pathlib import Path

from agent_template import AgentBuilder

agent = AgentBuilder(Path(__file__).parent / "config.yaml").build()
agent.serve(port=9000)  # A2A 端點: http://0.0.0.0:9000(card 在 /.well-known/agent-card.json)
