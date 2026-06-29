"""Regression: detectors must stay roughly linear on long adversarial output (no ReDoS)."""
import time

from agent_template._secure._rules import detect_pii


def test_email_detector_no_quadratic_blowup():
    # Long local-part-like run with no '@' would trigger O(n^2) backtracking
    # under an unbounded email regex. Bounded quantifiers keep it fast.
    payload = "a" * 200_000
    start = time.perf_counter()
    assert detect_pii(payload) == []
    assert time.perf_counter() - start < 1.0


def test_email_still_detected_after_bounding():
    assert detect_pii("reach me at jane.doe@corp.com") == ["pii: email"]
