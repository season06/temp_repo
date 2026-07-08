from agent_template.hooks import Hook, HookContext, StopRound


def test_stop_round_carries_reason():
    s = StopRound(reason="nope")
    assert s.reason == "nope"
    assert StopRound().reason is None


def test_hook_context_fields():
    ctx = HookContext(phase="before_tool", tool_name="ping", tool_args={"x": 1})
    assert ctx.phase == "before_tool"
    assert ctx.tool_name == "ping"
    assert ctx.tool_args == {"x": 1}
    assert ctx.messages is None
    assert ctx.result is None


def test_base_hook_methods_return_none():
    h = Hook()
    ctx = HookContext(phase="before_llm")
    assert h.before_llm(ctx) is None
    assert h.after_llm(ctx) is None
    assert h.before_tool(ctx) is None
    assert h.after_tool(ctx) is None


def test_subclass_can_return_stop_round():
    class Stopper(Hook):
        def before_tool(self, context):
            return StopRound(reason="blocked")

    result = Stopper().before_tool(HookContext(phase="before_tool"))
    assert isinstance(result, StopRound)
    assert result.reason == "blocked"
