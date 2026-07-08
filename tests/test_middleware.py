from langchain_core.messages import AIMessage, HumanMessage
from deepagents import create_deep_agent

from agent_template._middleware import HookMiddleware
from agent_template.hooks import Hook, StopRound
from tests.fakes import FakeToolModel, ping


class _Recorder(Hook):
    def __init__(self):
        self.seen = []

    def before_llm(self, context):
        self.seen.append("before_llm")

    def after_llm(self, context):
        self.seen.append("after_llm")


def test_before_model_runs_before_llm_hooks_and_continues():
    rec = _Recorder()
    mw = HookMiddleware([rec])
    state = {"messages": [HumanMessage(content="hi")]}
    assert mw.before_model(state, None) is None
    assert rec.seen == ["before_llm"]


def test_after_model_halts_on_llm_session_stop():
    mw = HookMiddleware([])
    stop_ai = AIMessage(content="bye", response_metadata={"status": "session_stop"})
    state = {"messages": [HumanMessage(content="hi"), stop_ai]}
    assert mw.after_model(state, None) == {"jump_to": "end"}


def test_before_model_halts_when_hook_returns_stop_round():
    class Stopper(Hook):
        def before_llm(self, context):
            return StopRound()

    mw = HookMiddleware([Stopper()])
    state = {"messages": [HumanMessage(content="hi")]}
    assert mw.before_model(state, None) == {"jump_to": "end"}


def test_integration_after_model_session_stop_ends_run_before_tool():
    # LLM 首則回應即帶 session_stop → 不應呼叫 tool
    model = FakeToolModel(scripted=[
        AIMessage(content="stop", response_metadata={"status": "session_stop"},
                  tool_calls=[{"name": "ping", "args": {"x": "hi"}, "id": "c1"}]),
        AIMessage(content="should-not-reach"),
    ])
    agent = create_deep_agent(model=model, tools=[ping], system_prompt="x",
                              middleware=[HookMiddleware([])])
    out = agent.invoke({"messages": [("user", "go")]})
    contents = [getattr(m, "content", None) for m in out["messages"]]
    assert "should-not-reach" not in contents
    assert all(type(m).__name__ != "ToolMessage" for m in out["messages"])
