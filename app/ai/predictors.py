# app/ai/predictors.py
from dataclasses import dataclass
from typing import Dict, Any

import numpy as np

from .model_loader import (
    get_eligibility_model,
    get_intent_model_and_vec,
    ModelFileMissing,
)
from app.engine.audit import risk_flag_from_prob


class EligibilityModelNotFound(RuntimeError):
    pass


class IntentModelNotFound(RuntimeError):
    pass


@dataclass
class EligOut:
    label: str
    prob: float
    risk_score: float
    risk_flag: bool


def predict_eligibility(features: Dict[str, Any]) -> Dict[str, Any]:
    """
    Thin wrapper around the eligibility model.
    """
    try:
        model = get_eligibility_model()
    except ModelFileMissing as e:
        raise EligibilityModelNotFound(str(e))

    # --- FIX STARTS HERE ---
    # 1. Use dtype=object to allow strings (Gender="F") and numbers mixed together
    # 2. Add the missing 'gender' field at index 1 to match training data
    x = np.array(
        [
            [
                features.get("age", 0),
                features.get("gender", "O"),      # <--- Was missing!
                features.get("income", 0),
                features.get("education_years", 0),
                features.get("rural", 0),
                features.get("caste_marginalized", 0),
            ]
        ],
        dtype=object,  # <--- Was 'float', caused crash with "F"
    )
    # --- FIX ENDS HERE ---

    # The pipeline handles the OneHotEncoding for gender automatically
    proba = model.predict_proba(x)[0, 1]
    prob = float(round(float(proba), 3))

    label = "likely" if prob >= 0.6 else "uncertain"
    risk_score = round(1.0 - prob, 3)
    
    # Pass the actual caste status to the audit rule
    risk_flag = risk_flag_from_prob(prob, features.get("caste_marginalized"))

    return {
        "label": label,
        "prob": prob,
        "risk_score": risk_score,
        "risk_flag": risk_flag,
    }


def classify_intent(text: str) -> tuple[str, float]:
    """
    TF-IDF + Naive Bayes text intent classifier.
    """
    try:
        nb, vec = get_intent_model_and_vec()
    except ModelFileMissing as e:
        raise IntentModelNotFound(str(e))

    X = vec.transform([text])
    proba = nb.predict_proba(X)[0]
    idx = int(proba.argmax())
    label = nb.classes_[idx]
    conf = float(round(float(proba[idx]), 3))
    return label, conf