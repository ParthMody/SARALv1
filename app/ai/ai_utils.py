# app/ai/ai_utils.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class AssistOut:
    review_confidence: float   # 0..1
    audit_flag: bool
    flag_reason: str
    intent_label: Optional[str] = None

def completeness_score(fields: dict) -> float:
    keys = ["scheme_code", "citizen_hash", "locale"]
    have = sum(1 for k in keys if fields.get(k))
    return round(have / len(keys), 2)

def clarity_score_from_text(text: Optional[str]) -> float:
    if not text:
        return 0.3
    t = text.lower()
    base = min(1.0, max(0.0, len(t) / 80))
    hints = any(w in t for w in ["apply", "status", "rejected", "help", "eligibility", "document"])
    return round(min(1.0, base + (0.2 if hints else 0.0)), 2)

def rule_checks(schema: dict) -> list[str]:
    reasons = []
    # put simple, explainable checks here later (doc presence, etc.)
    return reasons

def assistive_score(case_fields: dict, message_text: Optional[str]) -> AssistOut:
    comp = completeness_score(case_fields)
    clar = clarity_score_from_text(message_text)
    review_confidence = round(0.6 * comp + 0.4 * clar, 2)

    reasons = []
    if comp < 0.7: reasons.append("missing_fields")
    if clar < 0.5: reasons.append("low_message_clarity")
    reasons += rule_checks(case_fields)

    return AssistOut(
        review_confidence=review_confidence,
        audit_flag=bool(reasons),
        flag_reason="|".join(reasons)
    )

# Optional: intent classifier hooks (no exceptions required for v1)
def classify_intent(text: str) -> tuple[str, float]:
    # drop-in for your TF-IDF model when ready; placeholder for now
    t = text.lower()
    if "rejected" in t: return "rejected", 0.9
    if "apply" in t:    return "apply", 0.8
    if "status" in t:   return "status", 0.8
    if "help" in t:     return "help", 0.7
    return "other", 0.5
