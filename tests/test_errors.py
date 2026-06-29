import pytest
from agent_template.errors import (
    AgentTemplateError, ConfigError, ProviderError, SecurityViolation,
)

def test_exception_hierarchy():
    for exc in (ConfigError, ProviderError, SecurityViolation):
        assert issubclass(exc, AgentTemplateError)

def test_raise_and_catch_as_base():
    with pytest.raises(AgentTemplateError):
        raise ConfigError("bad config")
