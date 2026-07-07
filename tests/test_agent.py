from langchain_core.messages import HumanMessage
from a2a_mvp.config import Config
from a2a_mvp.agent import build_agent
from tests.stub import make_stub

CFG = Config()


def test_agent_runs_with_stub_model():
    agent = build_agent(CFG, model=make_stub("hello from agent"))
    result = agent.invoke({"messages": [HumanMessage(content="hi")]})
    final = result["messages"][-1].content
    assert "hello from agent" in final
