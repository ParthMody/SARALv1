# app/engine/rules.py
from dataclasses import dataclass
from typing import Dict, Any, List

from .scoring import completeness_score, clarity_score_from_text, combined_score


@dataclass
class AssistOut:
    """
    Single, explainable object returned by the rule engine.
    """
    review_confidence: float          # 0..1
    audit_flag: bool
    flag_reason: str                  # pipe-separated reasons or ""
    intent_label: str | None = None   # optional, can be set by NLP layer


def rule_checks(fields: Dict[str, Any]) -> List[str]:
    """
    Deterministic, documentable checks.

    These rules MUST stay simple and auditable. They are deliberately
    conservative and can be shown verbatim in documentation.
    """
    reasons: List[str] = []

    scheme = (fields.get("scheme_code") or "").upper()
    locale = (fields.get("locale") or "").lower()

    # Example: ensure locale is set for any scheme
    if not locale:
        reasons.append("missing_locale")

    # Example: PMAY may require more structured follow-up
    if scheme == "PMAY":
        # Placeholder rule to show extensibility
        # e.g., later: if not fields.get("has_address_proof"): reasons.append("missing_address_proof")
        pass

    return reasons


def assistive_decision(case_fields: Dict[str, Any], message_text: str | None) -> AssistOut:
    """
    Top-level function the rest of the app should call.

    Computes:
    - completeness and clarity scores
    - combined review_confidence
    - list of rule-based reasons → audit_flag + flag_reason
    """
    comp = completeness_score(case_fields)
    clar = clarity_score_from_text(message_text)
    review_confidence = combined_score(comp, clar)

    reasons: List[str] = []
    if comp < 0.7:
        reasons.append("missing_fields")
    if clar < 0.5:
        reasons.append("low_message_clarity")

    reasons.extend(rule_checks(case_fields))

    audit_flag = bool(reasons)
    flag_reason = "|".join(reasons)

    return AssistOut(
        review_confidence=review_confidence,
        audit_flag=audit_flag,
        flag_reason=flag_reason or "",
    )

def get_document_checklist(profile: dict, scheme_code: str) -> list[str]:
    docs = ["Aadhar Card"] # Base requirement

    if scheme_code == "UJJ":
        docs.append("Bank Account Passbook")
        if profile.get("caste_marginalized"):
             docs.append("Caste Certificate (SC/ST)")

    if scheme_code == "PMAY":
        if profile.get("income") < 300000:
            docs.append("Income Certificate (EWS)")

    return docs
