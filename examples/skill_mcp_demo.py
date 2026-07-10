"""Skill + MCP 自包含範例,並實際呼叫 agent。

三個部分:
  - skill:examples/skills/make_a_joke.py(一支 @tool 檔)
  - mcp  :examples/mcp/local_server.py(stdio FastMCP,提供 add / get)
  - 假模型:透過 register_provider 註冊一個 "fake" provider,用腳本化的
           AIMessage 強制觸發 skill 與 MCP 的 tool call,故不需 LLM 金鑰
           即可端到端跑起來。

執行:
  .venv/bin/python examples/skill_mcp_demo.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from deepagents import create_deep_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent_template.config import AgentSettings, Config
from agent_template.core import AgentBuilder, register_provider
from agent_template.hooks import HookMiddleware

HERE = Path(__file__).parent
SKILL_PATH = str(HERE / "skills" / "make_a_joke.py")
MCP_PATH = str(HERE / "mcp" / "local_server.py")


class ScriptedModel(BaseChatModel):
    """依序吐出腳本 AIMessage 的假模型(支援 bind_tools);跑完固定回最後一則,
    避免 deepagent 多呼叫幾次時 IndexError。"""

    scripted: list = []
    _cursor: dict = {}

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        i = self._cursor.setdefault(id(self), 0)
        message = self.scripted[min(i, len(self.scripted) - 1)]
        self._cursor[id(self)] = i + 1
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self):
        return "scripted"


# 腳本:先呼叫 skill make_a_joke,再呼叫 MCP tool add,最後不帶 tool_call → 結束。
_SCRIPT = [
    AIMessage(content="", tool_calls=[{"name": "make_a_joke", "args": {"topic": "cats"}, "id": "c1"}]),
    AIMessage(content="", tool_calls=[{"name": "add", "args": {"a": 2, "b": 3}, "id": "c2"}]),
    AIMessage(content="Done: joke told and 2+3 computed."),
]


def _register_fake_provider() -> None:
    """註冊一個用假模型的 provider,示範 register_provider 這個框架擴充點。
    簽章需與 build_deepagent 相同。"""
    model = ScriptedModel(scripted=_SCRIPT)

    def build_fake(config, hooks=None, tools=None, observability=None):
        middleware = [HookMiddleware(hooks)] if hooks else []
        return create_deep_agent(
            model=model,
            tools=tools or [],
            system_prompt=config.agent.system_prompt,
            middleware=middleware,
        )

    register_provider("fake", build_fake)


def build_demo_agent():
    """用 config.agent.provider="fake" 選到假模型 provider,並掛上 skill 與 MCP。"""
    _register_fake_provider()
    config = Config(agent=AgentSettings(provider="fake", system_prompt="you are a demo agent"))
    return (
        AgentBuilder(config)
        .add_skill("make_a_joke", SKILL_PATH)                      # 本地 @tool 檔
        .add_mcp("mathserver", "stdio", MCP_PATH, func=["add"])    # stdio MCP,只取 add
        .build()
    )


async def run(agent) -> None:
    # 掛了 MCP → 必須 ainvoke(MCP tool 為 async-only)。
    result = await agent.ainvoke({"messages": [("user", "tell a joke and add 2+3")]})
    for message in result["messages"]:
        message.pretty_print()


if __name__ == "__main__":
    # build() 內部用 asyncio.run 載入 MCP tools,故必須在進入事件迴圈「之前」建好 agent。
    demo_agent = build_demo_agent()
    asyncio.run(run(demo_agent))
