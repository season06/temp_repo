import re
import unicodedata

from ._envelope import BEGIN_MARKER, END_MARKER

# ---------------------------------------------------------------------------
# Prompt-injection detection
#
# 注意:這是「基準(baseline)」規則集,刻意求高訊號、低誤判;更進階的
# 正規化(leetspeak / homoglyph / base64 解碼)與間接注入屬 P3 範圍。
# ---------------------------------------------------------------------------
_INJECTION_PATTERNS = [
    # override 動詞 + 時序/system 詞 + 指令名詞(必須有指令名詞,降低誤判)
    r"(?:ignore|disregard|forget)\s+(?:all\s+|everything\s+|the\s+)?(?:your\s+|the\s+)?"
    r"(?:previous|above|prior|earlier|preceding|system)\s+"
    r"(?:instructions?|prompts?|rules?|directions?|guidelines?)",
    # 把「上面的文字」翻譯/重複/輸出的回顯攻擊
    r"(?:translate|repeat|summari[sz]e|rephrase|print|output|echo)\s+"
    r"(?:the\s+|all\s+|everything\s+)?(?:text|words|content|message|prompt|instructions?|everything)\s+"
    r"(?:above|before|preceding)",
    # 系統提示詞抽取:限 "your prompt" / "system prompt"(不抓裸 "the prompt",降低範本類誤判)
    r"(?:reveal|show|print|repeat|leak|tell\s+me|give\s+me|what(?:'?s| is))\b.{0,30}?"
    r"(?:your\s+(?:system\s+)?prompt|the\s+system\s+prompt)",
    # 系統指令抽取(instructions/rules 只有在前面有 system 才算)
    r"(?:reveal|show|print|repeat|leak)\b.{0,30}?(?:your|the)\s+system\s+"
    r"(?:instructions?|directives?|rules?)",
    # 抽取「你的(your)指令/規則」:限抽取動詞(reveal/repeat/leak/print)以降低誤判
    # (放掉 show/give/tell me:"show me your guidelines for X" 屬合法請求)
    r"(?:reveal|repeat|leak|print)\b.{0,30}?"
    r"your\s+(?:system\s+)?(?:instructions?|directives?|rules?|guidelines?)",
    # 人格接管 "you are now ..."(僅越獄/解除限制語彙)
    r"you\s+are\s+now\s+(?:a\s+|an\s+|in\s+)?(?:dan\b|jailbroken|unrestricted|uncensored|unfiltered|"
    r"freed?\s+from\s+(?:all\s+)?(?:your\s+)?(?:restrictions|rules|guidelines|constraints)|"
    r"developer\s+mode|no\s+longer\s+bound|not\s+bound\s+by)",
    # "act as ..." 人格 / roleplay 解除限制
    # (不收 "act as dan":Dan 為常見人名,易誤判;"you are now DAN" 由上方規則攔截)
    r"act\s+as\s+(?:an?\s+)?(?:developer\s+mode|"
    r"(?:unrestricted|unfiltered|jailbroken|uncensored)\s+(?:ai|model|assistant))",
    r"(?:pretend|roleplay|role-play)\b.{0,30}?"
    r"(?:no\s+(?:restrictions|rules|filter|limits|guidelines)|"
    r"without\s+(?:restrictions|rules|filters)|unrestricted|unfiltered|jailbroken|uncensored)",
    # 結構化角色偽造分隔符(僅比對帶分隔符的字面量)
    r"<\|\s*(?:im_start|im_end|system|assistant|user|endoftext)\s*\|>",
    r"\[/?INST\]|<</?SYS>>",
    # 中日韓(CJK)注入,收斂到明確的指令/提示詞語彙以降低誤判
    r"忽略\s*(以上|上述|之前|先前|前面|所有|全部)*\s*(的)?\s*(指令|指示|規則|提示詞)",
    r"(顯示|展示|告訴我|透露|洩漏|輸出|输出)\s*(你的|您的)?\s*(系統提示詞?|系統指令|提示詞|prompt)",
    r"(你現在(要|將)?扮演|假裝你是|假設你是|你現在是一[個名位])",
]
_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]

# ---------------------------------------------------------------------------
# PII / secrets detection
# ---------------------------------------------------------------------------
# 量詞上界化以避免長字串(無 @)時的二次方回溯(ReDoS);會跑在模型輸出上。
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,24}")
# 信用卡:先抓 13-19 碼候選(限 ASCII 數字,配合 _luhn_ok 的 ord 運算),再用 Luhn 過濾
# (濾掉 ISBN-13 / 時間戳等誤判;15 碼 IMEI 為 Luhn-valid 會殘留誤判,v1 接受,
#  見 docs/superpowers/specs/p2-redteam-deferred-to-p3.md)
_CC_CANDIDATE_RE = re.compile(r"\b[0-9](?:[ -]?[0-9]){12,18}\b")
# 美國 SSN:僅比對有連字號的 ddd-dd-dddd(排除無效區段;不抓裸 9 碼以降低誤判)
_SSN_RE = re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")

# 機密金鑰:大小寫敏感(前綴本身就是固定大小寫,不可用 IGNORECASE)
_SECRET_PATTERNS = {
    "pii: secret:private_key": re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"
    ),
    "pii: secret:aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "pii: secret:github_pat": re.compile(r"\bghp_[A-Za-z0-9]{36,}\b"),
    "pii: secret:google_api_key": re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    "pii: secret:slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "pii: secret:stripe_key": re.compile(r"\bsk_live_[0-9A-Za-z]{16,}\b"),
    "pii: secret:jwt": re.compile(r"\beyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b"),
}


def _normalize(text):
    # NFKC 折疊樣式化字元(fullwidth、數學粗體等),並移除 Cf 類隱形字元
    # (zero-width space / joiner、BOM、soft-hyphen),NBSP(Zs)保留交給 \s。
    text = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def _luhn_ok(digits):
    total = 0
    parity = len(digits) % 2
    for i, ch in enumerate(digits):
        d = ord(ch) - 48
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def detect_prompt_injection(text) -> list:
    if not text:
        return []
    norm = _normalize(text)
    return [f"prompt_injection: {rx.pattern}" for rx in _INJECTION_RE if rx.search(norm)]


def detect_pii(text) -> list:
    if not text:
        return []
    # 輸出側同樣做正規化:擋住 fullwidth/zero-width 混淆的卡號/機密/sentinel 外洩。
    text = _normalize(text)
    hits = []
    if _EMAIL_RE.search(text):
        hits.append("pii: email")
    for m in _CC_CANDIDATE_RE.finditer(text):
        digits = m.group().replace(" ", "").replace("-", "")
        if 13 <= len(digits) <= 19 and digits.isdigit() and _luhn_ok(digits):
            hits.append("pii: credit_card")
            break
    if _SSN_RE.search(text):
        hits.append("pii: ssn")
    for name, rx in _SECRET_PATTERNS.items():
        if rx.search(text):
            hits.append(name)
    return hits


def detect_system_prompt_leak(text) -> list:
    # 僅比對機器插入的字面 sentinel,誤判趨近於零(刻意不做語意/改寫比對)。
    if not text:
        return []
    text = _normalize(text)  # 擋住以 zero-width 等混淆 sentinel 規避偵測
    hits = []
    if BEGIN_MARKER in text:
        hits.append("system_prompt_leak: BEGIN_MARKER")
    if END_MARKER in text:
        hits.append("system_prompt_leak: END_MARKER")
    return hits
