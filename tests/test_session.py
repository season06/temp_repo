from langchain_core.messages import AIMessage, ToolMessage

from agent_template.hooks import is_session_stop, SESSION_STOP


def test_session_stop_constant():
    assert SESSION_STOP == "session_stop"


def test_none_is_not_session_stop():
    assert is_session_stop(None) is False


def test_ai_message_without_marker():
    assert is_session_stop(AIMessage(content="hi")) is False


def test_ai_message_response_metadata_marker():
    msg = AIMessage(content="x", response_metadata={"status": "session_stop"})
    assert is_session_stop(msg) is True


def test_tool_message_additional_kwargs_marker():
    msg = ToolMessage(content="x", tool_call_id="c1", additional_kwargs={"status": "session_stop"})
    assert is_session_stop(msg) is True


def test_tool_message_other_status_is_not_stop():
    msg = ToolMessage(content="x", tool_call_id="c1", response_metadata={"status": "ok"})
    assert is_session_stop(msg) is False
