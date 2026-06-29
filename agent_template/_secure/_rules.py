import re

# prompt injection:常見覆蓋/越權樣式(大小寫不敏感)
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|above|prior)\s+instructions",
    r"disregard\s+(the\s+)?(previous|above|system)",
    r"reveal\s+your\s+(system\s+)?prompt",
    r"show\s+me\s+your\s+(system\s+)?prompt",
    r"you\s+are\s+now\s+",
    r"act\s+as\s+(?:a\s+)?(?:dan|developer\s+mode)",
]
_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]

# PII:email、信用卡號(13-16 碼,允許空白/連字號分隔)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_CC_RE = re.compile(r"\b(?:\d[ -]?){13,16}\b")


def detect_prompt_injection(text) -> list:
    if not text:
        return []
    return [f"prompt_injection: {rx.pattern}" for rx in _INJECTION_RE if rx.search(text)]


def detect_pii(text) -> list:
    if not text:
        return []
    hits = []
    if _EMAIL_RE.search(text):
        hits.append("pii: email")
    if _CC_RE.search(text):
        hits.append("pii: credit_card")
    return hits
