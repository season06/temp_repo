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


from langchain_core.messages import ToolMessage as _ToolMessage


class _FakeRequest:
    def __init__(self, tool_call):
        self.tool_call = tool_call


def test_wrap_tool_call_runs_tool_and_after_hook_when_allowed():
    seen = []

    class Watcher(Hook):
        def before_tool(self, context):
            seen.append(("before_tool", context.tool_name, context.tool_args))

        def after_tool(self, context):
            seen.append(("after_tool", context.result.content))

    mw = HookMiddleware([Watcher()])
    req = _FakeRequest({"name": "ping", "args": {"x": "hi"}, "id": "c1", "type": "tool_call"})
    handler_called = []

    def handler(r):
        handler_called.append(True)
        return _ToolMessage(content="pong:hi", tool_call_id="c1", name="ping")

    result = mw.wrap_tool_call(req, handler)
    assert handler_called == [True]
    assert result.content == "pong:hi"
    assert seen == [("before_tool", "ping", {"x": "hi"}), ("after_tool", "pong:hi")]


def test_before_tool_stop_round_short_circuits_tool():
    class Denier(Hook):
        def before_tool(self, context):
            return StopRound(reason="denied")

    mw = HookMiddleware([Denier()])
    req = _FakeRequest({"name": "ping", "args": {"x": "hi"}, "id": "c1", "type": "tool_call"})
    handler_called = []

    def handler(r):
        handler_called.append(True)
        return _ToolMessage(content="pong", tool_call_id="c1", name="ping")

    result = mw.wrap_tool_call(req, handler)
    assert handler_called == []  # tool did NOT run
    assert isinstance(result, _ToolMessage)
    assert result.response_metadata.get("status") == "session_stop"
    assert result.tool_call_id == "c1"


def test_integration_before_tool_deny_halts_round_and_skips_tool():
    ran = []

    class Denier(Hook):
        def before_tool(self, context):
            return StopRound()

    from tests.fakes import FakeToolModel
    from langchain_core.tools import tool

    @tool
    def rec(x: str) -> str:
        """records"""
        ran.append(x)
        return "ran"

    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "rec", "args": {"x": "hi"}, "id": "c1"}]),
        AIMessage(content="should-not-reach"),
    ])
    agent = create_deep_agent(model=model, tools=[rec], system_prompt="x",
                              middleware=[HookMiddleware([Denier()])])
    out = agent.invoke({"messages": [("user", "go")]})
    contents = [getattr(m, "content", None) for m in out["messages"]]
    assert ran == []  # tool never executed
    assert "should-not-reach" not in contents  # round halted


def test_integration_tool_result_session_stop_halts_before_next_llm():
    from tests.fakes import FakeToolModel
    from langchain_core.tools import tool

    @tool
    def stopper(x: str) -> str:
        """returns a plain value; middleware marks stop via metadata path in real mcp"""
        return "ok"

    # Simulate a tool whose ToolMessage carries session_stop by using an after_tool hook
    class MarkStop(Hook):
        def after_tool(self, context):
            return StopRound()

    model = FakeToolModel(scripted=[
        AIMessage(content="", tool_calls=[{"name": "stopper", "args": {"x": "hi"}, "id": "c1"}]),
        AIMessage(content="should-not-reach"),
    ])
    agent = create_deep_agent(model=model, tools=[stopper], system_prompt="x",
                              middleware=[HookMiddleware([MarkStop()])])
    out = agent.invoke({"messages": [("user", "go")]})
    contents = [getattr(m, "content", None) for m in out["messages"]]
    assert "should-not-reach" not in contents
