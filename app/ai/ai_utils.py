# app/ai/ai_utils.py
import pathlib, pickle, numpy as np

# This file is inside app/ai/, so parents[1] == app/
APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
MODELS = APP_ROOT / "ai" / "models"

class EligibilityModelNotFound(FileNotFoundError): ...
class IntentModelNotFound(FileNotFoundError): ...

_elig = _clf = _vec = None

def load_elig():
    global _elig
    if _elig is None:
        p = MODELS / "eligibility.pkl"
        if not p.exists():
            raise EligibilityModelNotFound(f"eligibility.pkl not found at {p}")
        with open(p, "rb") as f:
            _elig = pickle.load(f)
    return _elig

def load_intent():
    global _clf, _vec
    if _clf is None or _vec is None:
        p1, p2 = MODELS / "intent_nb.pkl", MODELS / "intent_vectorizer.pkl"
        if not p1.exists() or not p2.exists():
            raise IntentModelNotFound(f"intent model/vectorizer missing at {p1}, {p2}")
        with open(p1, "rb") as f:
            _clf = pickle.load(f)
        with open(p2, "rb") as f:
            _vec = pickle.load(f)
    return _clf, _vec

def predict_eligibility(row: dict):
    """
    row keys: age, gender ('M'/'F'), income, education_years, rural (0/1), caste_marginalized (0/1)
    """
    model = load_elig()
    X = np.array([[row["age"], row["gender"], row["income"], row["education_years"],
                   int(row["rural"]), int(row["caste_marginalized"])]], dtype=object)
    proba = float(model.predict_proba(X)[0][1])
    label = "likely" if proba >= 0.6 else ("uncertain" if proba >= 0.4 else "unlikely")
    # simple risk
    low_income = 1.0 if row["income"] < 120000 else 0.0
    risk = round(0.5*(1-proba) + 0.5*low_income, 3)
    fairness_flag = (row["caste_marginalized"] == 1 and proba < 0.4 and row["income"] < 120000)
    return {"label": label, "prob": round(proba, 3), "risk_score": risk, "risk_flag": bool(fairness_flag)}

def classify_intent(text: str):
    clf, vec = load_intent()
    X = vec.transform([text])
    probs = clf.predict_proba(X)[0]
    idx = int(probs.argmax())
    return clf.classes_[idx], float(probs[idx])
