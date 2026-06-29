import agent_template


def test_validator_exported():
    assert hasattr(agent_template, "Validator")
    assert "Validator" in agent_template.__all__
