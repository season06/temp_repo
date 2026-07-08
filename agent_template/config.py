class AgentConfig:
    """單一 agent 的 LLM 設定（OpenAI-compatible 端點）。"""

    def __init__(self, api_key, base_url, model, temperature=0.0, system_prompt=None):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.system_prompt = system_prompt
