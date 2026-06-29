from deepagents import create_deep_agent

from .config import AgentConfig
from .errors import ConfigError
from .observability import audit
from .providers import build_chat_model
from ._secure import build_security_middleware, wrap_system_prompt
from ._secure._agent import SecureAgent


def _build_deep_agent(model, tools: list, system_prompt, middleware: list):
    # 隔離 deepagents 呼叫:版本差異只改這裡。
    return create_deep_agent(
        model=model, tools=tools, system_prompt=system_prompt, middleware=middleware,
    )


def build_agent(task_prompt, tools: list = None, config: AgentConfig = None,
                output_validators: list = None):
    if config is None:
        raise ConfigError("build_agent 需要 AgentConfig")
    tools = tools or []
    model = build_chat_model(config)
    # 安全外殼:夾心 prompt + 強制 middleware(永遠存在,無法關閉)。
    system_prompt = wrap_system_prompt(task_prompt)
    middleware = build_security_middleware(output_validators)
    agent = _build_deep_agent(model, tools, system_prompt, middleware)
    if config.enable_audit_log:
        audit({"action": "build_agent", "tools": len(tools)})
    # 包一層 SecureAgent:停用會繞過輸出驗證的串流方法。
    return SecureAgent(agent)
