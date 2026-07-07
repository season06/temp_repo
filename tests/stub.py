from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


class ToolAwareFakeModel(GenericFakeChatModel):
    """deepagents 會對 model 呼叫 bind_tools;GenericFakeChatModel 未實作,
    這裡回傳 self(fake 不需真的綁工具,只固定吐 AIMessage)。"""

    def bind_tools(self, tools, **kwargs):
        return self


def make_stub(text, n=5):
    return ToolAwareFakeModel(messages=iter([AIMessage(content=text)] * n))
