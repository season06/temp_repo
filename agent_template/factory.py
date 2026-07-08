from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI


def _build_llm(config):
    return ChatOpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        temperature=config.temperature,
    )


def build_agent(config):
    """建構並回傳原生 DeepAgent 物件（執行期回歸原生,無包裝）。"""
    llm = _build_llm(config)
    return create_deep_agent(
        model=llm,
        tools=[],
        system_prompt=config.system_prompt,
    )
