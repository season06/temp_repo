import asyncio

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessageChunk

from agent_template.core.agent import Agent


class FakeNative:
    """模擬 deepagents/LangGraph 原生 agent 的 async 介面。"""

    def __init__(self, chunks=None, error=None):
        self.calls = []
        self.chunks = chunks if chunks is not None else [
            (AIMessageChunk(content="hel"), {}),
            (AIMessageChunk(content=""), {}),  # 空 content 要濾掉
            (ToolMessageChunk(content="tool noise", tool_call_id="t1"), {}),  # 非 AI chunk 要濾掉
            (AIMessageChunk(content="lo"), {}),
        ]
        self.error = error

    async def ainvoke(self, payload):
        self.calls.append(("ainvoke", payload))
        return {"messages": [HumanMessage("hi"), AIMessage("hello there")]}

    async def astream(self, payload, stream_mode=None):
        self.calls.append(("astream", payload, stream_mode))
        if self.error:
            raise self.error
        if stream_mode == "messages":
            for item in self.chunks:
                yield item
        else:
            yield "raw-chunk"  # dict 透傳路徑的原生行為


def test_invoke_str_in_str_out():
    native = FakeNative()
    agent = Agent(native)
    assert agent.invoke("hi") == "hello there"
    assert native.calls == [
        ("ainvoke", {"messages": [{"role": "user", "content": "hi"}]})
    ]


def test_invoke_dict_passthrough_returns_native_state():
    agent = Agent(FakeNative())
    payload = {"messages": [{"role": "user", "content": "hi"}]}
    result = agent.invoke(payload)
    assert result["messages"][-1].content == "hello there"  # 整包 state


def test_ainvoke_str():
    agent = Agent(FakeNative())
    assert asyncio.run(agent.ainvoke("hi")) == "hello there"


def test_stream_str_yields_only_ai_text():
    agent = Agent(FakeNative())
    assert list(agent.stream("hi")) == ["hel", "lo"]


def test_stream_dict_passthrough():
    agent = Agent(FakeNative())
    payload = {"messages": [{"role": "user", "content": "hi"}]}
    assert list(agent.stream(payload)) == ["raw-chunk"]


def test_astream_str():
    agent = Agent(FakeNative())

    async def collect():
        return [c async for c in agent.astream("hi")]

    assert asyncio.run(collect()) == ["hel", "lo"]


def test_stream_propagates_error():
    agent = Agent(FakeNative(error=RuntimeError("model down")))
    with pytest.raises(RuntimeError, match="model down"):
        list(agent.stream("hi"))


def test_native_is_exposed():
    native = FakeNative()
    assert Agent(native).native is native
