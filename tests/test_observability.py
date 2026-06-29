import logging
from agent_template.observability import get_logger, audit, UsageTracker


def test_get_logger_returns_named_logger():
    log = get_logger("agent_template.test")
    assert isinstance(log, logging.Logger)
    assert log.name == "agent_template.test"


def test_audit_emits_record(caplog):
    with caplog.at_level(logging.INFO, logger="agent_template.audit"):
        audit({"action": "build_agent", "ok": True})
    assert any("build_agent" in r.getMessage() for r in caplog.records)


def test_usage_tracker_accumulates():
    t = UsageTracker()
    t.record(10, 5)
    t.record(3, 2)
    s = t.summary()
    assert s == {"prompt_tokens": 13, "completion_tokens": 7,
                 "total_tokens": 20, "calls": 2}


def test_get_logger_idempotent_handlers():
    log1 = get_logger("agent_template.idem_test")
    n_after_first = len(log1.handlers)
    log2 = get_logger("agent_template.idem_test")
    assert log1 is log2
    assert len(log2.handlers) == n_after_first == 1
