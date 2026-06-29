import agent_template


def test_public_surface():
    for name in ("build_agent", "AgentConfig", "AgentTemplateError",
                 "ConfigError", "ProviderError", "SecurityViolation", "__version__"):
        assert hasattr(agent_template, name), name


def test_private_modules_not_exported():
    # 私有實作不應出現在 __all__
    assert "providers" not in agent_template.__all__
    assert "factory" not in agent_template.__all__
