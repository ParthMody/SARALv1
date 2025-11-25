# app/ai/ai_utils.py
"""
Compatibility façade for all AI functionality.

External routes call:
- predict_eligibility(...)
- classify_intent(...)
- assistive_score(...)

but actual logic lives in:
- app.ai.predictors
- app.engine.rules
"""

from typing import Dict, Any

from .predictors import (
    predict_eligibility as _predict_eligibility,
    classify_intent as _classify_intent,
    EligibilityModelNotFound,
    IntentModelNotFound,
)

from app.engine.rules import (
    assistive_decision,
    AssistOut,
)


# -------------------------------
#  Public-facing wrapper functions
# -------------------------------

def predict_eligibility(features: Dict[str, Any]) -> Dict[str, Any]:
    """
    Thin wrapper so the rest of the application stays stable.
    """
    return _predict_eligibility(features)


def classify_intent(text: str):
    """
    Thin wrapper for NB classifier.
    """
    return _classify_intent(text)


def assistive_score(case_fields: Dict[str, Any], message_text: str | None) -> AssistOut:
    """
    Wrapper for deterministic assistive logic.
    """
    return assistive_decision(case_fields, message_text)


# -------------------------------
# Re-export error types so routes don’t break
# -------------------------------
__all__ = [
    "predict_eligibility",
    "classify_intent",
    "assistive_score",
    "AssistOut",
    "EligibilityModelNotFound",
    "IntentModelNotFound",
]
