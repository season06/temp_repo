from deepagents import create_deep_agent

from .config import AgentConfig
from .errors import ConfigError
from .observability import audit
from .providers import build_chat_model


def _build_deep_agent(model, tools: list, system_prompt):
    # 隔離 deepagents 呼叫:版本差異只改這裡。
    return create_deep_agent(model=model, tools=tools, system_prompt=system_prompt)


def build_agent(task_prompt, tools: list = None, config: AgentConfig = None):
    if config is None:
        raise ConfigError("build_agent 需要 AgentConfig")
    tools = tools or []
    model = build_chat_model(config)
    # P1 接縫:安全外殼在 P2 接管,屆時改為夾心組裝。
    system_prompt = task_prompt
    agent = _build_deep_agent(model, tools, system_prompt)
    if config.enable_audit_log:
        audit({"action": "build_agent", "tools": len(tools)})
    return agent
