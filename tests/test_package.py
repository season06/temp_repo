def test_package_imports_and_has_version():
    import agent_template
    assert isinstance(agent_template.__version__, str)
    assert agent_template.__version__
