"""Minimal offline deepagents demo.

This single-file module is compiled by Nuitka into ``agent_demo.so`` and shipped
as a wheel. It builds a tiny deep agent backed by a fake chat model, so it runs
fully offline with no API key.
"""

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from deepagents import create_deep_agent


def add(a, b):
    """Add two numbers and return the sum."""
    return a + b


def _fake_messages():
    # Infinite generator so any number of agent turns is fine (never StopIteration).
    while True:
        yield AIMessage(content="The sum of 2 and 3 is 5.")


class _FakeChatModel(GenericFakeChatModel):
    """Offline chat model that also accepts tool binding (the agent stack calls
    ``bind_tools``). It ignores the tools and just replays canned messages."""

    def bind_tools(self, tools, **kwargs):
        return self


def _build_agent():
    # Fake model: no network, no API key — deterministic output for the demo.
    model = _FakeChatModel(messages=_fake_messages())
    return create_deep_agent(
        tools=[add],
        system_prompt="You are a tiny demo agent that can add numbers.",
        model=model,
    )


def run(prompt="What is 2 + 3?"):
    """Run the agent once and return its final text response."""
    agent = _build_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    return result["messages"][-1].content


def main():
    print(run())


if __name__ == "__main__":
    main()
