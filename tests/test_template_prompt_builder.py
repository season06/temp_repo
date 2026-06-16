from rag_adapter.prompts.template_prompt_builder import TemplatePromptBuilder


def test_default_template_includes_context_and_query():
    prompt = TemplatePromptBuilder().build_prompt("what is x?", "x is a thing")

    assert "x is a thing" in prompt
    assert "what is x?" in prompt


def test_custom_template():
    builder = TemplatePromptBuilder(template="C={context} Q={query}")

    assert builder.build_prompt("q1", "c1") == "C=c1 Q=q1"
