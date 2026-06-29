from langchain_openai import ChatOpenAI

from .errors import ProviderError


def build_chat_model(config):
    try:
        return ChatOpenAI(
            model=config.model,
            base_url=config.base_url,
            api_key=config.api_key,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )
    except Exception as exc:
        raise ProviderError(f"建立 chat model 失敗: {exc}") from exc
