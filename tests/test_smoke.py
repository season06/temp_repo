import agent_template


def test_package_imports_with_version():
    assert agent_template.__version__ == "0.1.0"
