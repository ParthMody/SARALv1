from dataclasses import dataclass, field
from typing import List
from .scheme_config import get_scheme_config
from .audit import risk_flag_from_prob
from .near_miss import check_near_miss

@dataclass
class AssistOut:
    review_confidence: float
    audit_flag: bool
    flag_reason: str
    is_near_miss: bool = False
    alternatives: List[str] = field(default_factory=list)

def assistive_decision(
    scheme_code: str,
    profile: dict,
    message_text: str | None
) -> AssistOut:
    """
    Deterministic rules + near-miss + audit wiring.
    """
    config = get_scheme_config(scheme_code)

    # 1. Invalid Scheme Check
    if not config:
        return AssistOut(0.0, True, "invalid_scheme")

    criteria = config["criteria"]
    reasons: List[str] = []
    alternatives: List[str] = []

    # --- GENERIC CRITERIA CHECK ---

    # Age
    if profile.get("age", 0) < criteria.get("min_age", 0):
        reasons.append(f"Age must be {criteria['min_age']}+")

    # Gender
    allowed_genders = criteria.get("gender", [])
    if allowed_genders and profile.get("gender") not in allowed_genders:
        reasons.append(f"Scheme only for {allowed_genders}")

    # Income
    limit = criteria.get("max_income")
    income = profile.get("income", 0)
    if limit and income > limit:
        reasons.append(f"Income > {limit}")

    # Rural requirement
    if criteria.get("must_be_rural") and profile.get("rural") != 1:
        reasons.append("Must be Rural")

    # --- SCORING & NEAR-MISS / CONTEXT WIRING ---

    if not reasons:
        # Eligible by rules
        confidence = 0.9
        audit_flag = False
        is_near_miss = False
        alternatives = []
    else:
        # Failed at least one rule
        confidence = 0.1
        audit_flag = True
        is_near_miss = False
        alternatives = config.get("alternatives", [])

        # Near-miss check
        nm = check_near_miss(profile, scheme_code)

        if nm.is_near_miss and nm.counterfactual:
            is_near_miss = True
            reasons.append(f"Near Miss: {nm.counterfactual}")

        # Merge any contextual alternatives (e.g., MGNREGA) regardless of near-miss flag
        if nm.alternatives:
            alternatives = list(set(alternatives + nm.alternatives))

    # Audit Engine (fairness-aware flag)
    risk_flag = risk_flag_from_prob(confidence, profile.get("caste_marginalized"))
    final_audit = audit_flag or risk_flag

    return AssistOut(
        review_confidence=confidence,
        audit_flag=final_audit,
        flag_reason="|".join(reasons),
        is_near_miss=is_near_miss,
        alternatives=alternatives
    )
