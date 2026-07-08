from langchain_openai import ChatOpenAI


def _build_llm(config):
    return ChatOpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        temperature=config.temperature,
    )
