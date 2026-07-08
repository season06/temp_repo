from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.tools import tool


@tool
def ping(x: str) -> str:
    """returns pong"""
    return "pong:" + x


class FakeToolModel(BaseChatModel):
    """支援 bind_tools 的腳本化 chat model:依序吐出 scripted 內的 AIMessage。"""

    scripted: list = []
    _cursor: dict = {}

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        i = self._cursor.setdefault(id(self), 0)
        message = self.scripted[i]
        self._cursor[id(self)] = i + 1
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self):
        return "fake-tool"
