import agent_template


def test_public_surface():
    for name in ("build_agent", "AgentConfig", "AgentTemplateError",
                 "ConfigError", "ProviderError", "SecurityViolation", "__version__"):
        assert hasattr(agent_template, name), name


def test_all_is_exact_surface():
    assert set(agent_template.__all__) == {
        "build_agent", "AgentConfig", "AgentTemplateError",
        "ConfigError", "ProviderError", "SecurityViolation", "__version__",
    }


def test_private_modules_fully_excluded():
    for mod in ("factory", "providers", "config", "errors", "observability"):
        assert mod not in agent_template.__all__
