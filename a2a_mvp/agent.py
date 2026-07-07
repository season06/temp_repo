from deepagents import create_deep_agent
from a2a_mvp.tools import build_tools

SYSTEM_PROMPT = (
    "你是一個助理 agent。能用本地工具,必要時可用 call_remote_agent "
    "把子任務委派給其他 A2A agent。回答精簡。"
)


def build_agent(config, model=None):
    if model is None:
        from langchain_openai import ChatOpenAI
        model = ChatOpenAI(
            base_url=config.llm_base_url,
            api_key=config.llm_api_key,
            model=config.llm_model,
        )
    return create_deep_agent(
        model=model,
        tools=build_tools(config),
        system_prompt=SYSTEM_PROMPT,
    )
