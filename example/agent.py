from pathlib import Path

from agent_template import AgentBuilder

agent = AgentBuilder(Path(__file__).parent / "config.yaml").build()

print(agent.invoke("what time is it"))

for text in agent.stream("用俳句介紹你自己"):
    print(text, end="", flush=True)
print()
