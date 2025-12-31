# app/engine/rules.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .scheme_config import get_scheme_config


@dataclass
class RuleOut:
    rule_result: str  # ELIGIBLE_BY_RULE / INELIGIBLE_BY_RULE / UNKNOWN_NEEDS_DOCS
    reasons: List[str] = field(default_factory=list)
    alternatives: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)  # non-decision metadata


def _annualize_income(income: int, period: str) -> int:
    if period == "annual":
        return income
    if period == "monthly":
        return income * 12
    raise ValueError("Invalid income period")


def assistive_decision(scheme_code: str, profile: dict) -> RuleOut:
    cfg = get_scheme_config(scheme_code)
    if not cfg:
        return RuleOut(
            "UNKNOWN_NEEDS_DOCS",
            ["Invalid scheme code"],
            [],
            [],
        )

    criteria = cfg.get("criteria", {}) or {}
    reasons: List[str] = []
    alts: List[str] = list(cfg.get("alternatives", []) or [])
    tags: List[str] = []

    # ---------- inputs ----------
    age = int(profile.get("age") or 0)
    gender = profile.get("gender")
    rural = int(profile.get("rural") or 0)
    caste_flag = int(profile.get("caste_marginalized") or 0)

    income = profile.get("income")
    income_period = profile.get("income_period")

    # ---------- hard guards ----------
    # If income missing, rules cannot conclude; route to docs.
    if income is None or income_period is None:
        return RuleOut(
            "UNKNOWN_NEEDS_DOCS",
            ["Income or income period missing"],
            alts,
            tags,
        )

    try:
        annual_income = _annualize_income(int(income), str(income_period))
    except Exception:
        return RuleOut(
            "UNKNOWN_NEEDS_DOCS",
            ["Invalid income format"],
            alts,
            tags,
        )

    # ---------- deterministic checks ----------
    min_age = int(criteria.get("min_age") or 0)
    if min_age and age < min_age:
        reasons.append(f"Age must be {min_age}+")

    allowed_genders = criteria.get("gender") or []
    if allowed_genders and gender not in allowed_genders:
        reasons.append("Applicant category not eligible")

    if bool(criteria.get("must_be_rural")) and rural != 1:
        reasons.append("Must be Rural")

    # ---------- income band logic (config-driven) ----------
    bands = criteria.get("income_bands") or []
    matched_band = None
    for band in bands:
        try:
            if annual_income <= int(band.get("max", -1)):
                matched_band = str(band.get("name", ""))
                break
        except Exception:
            continue

    if bands and not matched_band:
        reasons.append("Income exceeds all eligible bands")
    elif matched_band:
        tags.append(f"{scheme_code}_BAND:{matched_band}")

    # ---------- caste logic (binary by design) ----------
    if bool(criteria.get("requires_marginalized")) and caste_flag != 1:
        reasons.append("Must belong to eligible social category")

    # ---------- final outcome ----------
    if not reasons:
        return RuleOut("ELIGIBLE_BY_RULE", [], [], tags)

    # IMPORTANT: keep alts for ineligible/unknown flows (triage, not auto-reject)
    return RuleOut("INELIGIBLE_BY_RULE", reasons, alts, tags)
