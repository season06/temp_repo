from langchain_core.messages import AIMessage
from deepagents import create_deep_agent

from tests.fakes import FakeToolModel, ping


def test_fake_tool_model_drives_a_full_tool_loop():
    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "ping", "args": {"x": "hi"}, "id": "c1"}]),
        AIMessage(content="done"),
    ])
    agent = create_deep_agent(model=model, tools=[ping], system_prompt="x")
    out = agent.invoke({"messages": [("user", "go")]})
    kinds = [type(m).__name__ for m in out["messages"]]
    assert "ToolMessage" in kinds
    assert out["messages"][-1].content == "done"
