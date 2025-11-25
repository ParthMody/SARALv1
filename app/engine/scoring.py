# app/engine/scoring.py
from dataclasses import dataclass
from typing import Dict, Any


def completeness_score(fields: Dict[str, Any]) -> float:
    """
    Score 0..1 based on presence / non-emptiness of key fields.
    Only looks at structural presence, not content.
    """
    keys = ["scheme_code", "citizen_hash", "locale"]
    if not keys:
        return 1.0
    have = sum(1 for k in keys if fields.get(k))
    return round(have / len(keys), 2)


def clarity_score_from_text(text: str | None) -> float:
    """
    Very light proxy for message clarity:
    - length (up to ~80 chars)
    - presence of some intent-like keywords
    """
    if not text:
        return 0.3

    t = text.lower().strip()
    base = min(1.0, max(0.0, len(t) / 80.0))
    hints = any(
        w in t
        for w in ["apply", "status", "rejected", "help", "eligibility", "document"]
    )
    score = base + (0.2 if hints else 0.0)
    return round(min(1.0, score), 2)


def combined_score(completeness: float, clarity: float) -> float:
    """
    Linear combination used everywhere so it is documented in one place.
    """
    score = 0.6 * completeness + 0.4 * clarity
    return round(max(0.0, min(1.0, score)), 2)
