class AgentTemplateError(Exception):
    """agent_template 所有例外的基底。"""


class ConfigError(AgentTemplateError):
    """設定不合法。"""


class ProviderError(AgentTemplateError):
    """LLM provider 建立或呼叫失敗。"""


class SecurityViolation(AgentTemplateError):
    """安全層攔截到違規(輸入防護 / 輸出驗證 / 完整性檢查)。"""
