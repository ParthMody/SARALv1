# scripts/seed_vignettes.py
"""
Stub vignette seeder for SARAL v2.
Generates 320 synthetic cases: 80 × (control/approve, control/reject,
treatment/approve, treatment/reject).

Stub field notes are clearly marked as placeholders — replace with
authentic SRA Annexure-II format once confirmed by field contact.

Usage:
    python -m scripts.seed_vignettes          # seed with defaults
    python -m scripts.seed_vignettes --clear  # drop existing pool first
"""
from __future__ import annotations

import argparse
import random
import sys
import os

# ── allow running from project root ──────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal, engine
from app.models import Base, ArmEnum, AlgoRecommendationEnum, RuleResultEnum, Vignette

# ── Reproducible stub pool ────────────────────────────────────────────────────
SEED = 42
RNG  = random.Random(SEED)

POOL_VERSION = "v2.0-stub"

# ── Profile building blocks ───────────────────────────────────────────────────
INCOMES_MONTHLY = [2000, 3500, 4200, 5000, 6500, 7800, 9000, 10500, 12000, 15000]
AGES            = list(range(21, 65))
HOUSING_STATUSES = ["kutcha", "semi-pucca", "rented", "homeless", "chawl"]

# Operator-visible fields only (TDD decision: show selective subset)
VISIBLE_PROFILE_KEYS = [
    "age", "income", "income_period",
    "rural", "caste_marginalized", "housing_status",
]

def _make_profile() -> dict:
    """
    Full profile for seeding. Backend uses all fields.
    Operator-visible subset is filtered at serve time in session.py.
    """
    return {
        # Operator-visible
        "age":               RNG.choice(AGES),
        "income":            RNG.choice(INCOMES_MONTHLY),
        "income_period":     "monthly",
        "rural":             RNG.choice([0, 1]),
        "caste_marginalized": RNG.choice([0, 1]),
        "housing_status":    RNG.choice(HOUSING_STATUSES),
        # Backend-only (not shown to operator)
        "gender":            RNG.choice(["M", "F", "O"]),
        "education_years":   RNG.randint(0, 16),
    }


# ── Stub field note generators ────────────────────────────────────────────────
# IMPORTANT: These are structural placeholders only.
# Language register, abbreviations, and information structure must match
# authentic SRA Annexure-II intake note format — pending field contact input.
# Marathi translations must be verified by a domain-familiar speaker (TDD §7.2).

def _control_note_en(profile: dict) -> str:
    """
    Sterile note: restates structured inputs only.
    Zero marginal information beyond profile fields (TDD §7.1).
    """
    rural_str   = "rural area" if profile["rural"] else "urban area"
    caste_str   = "belongs to marginalized caste category" if profile["caste_marginalized"] else "general category"
    housing_str = profile.get("housing_status", "unknown")
    return (
        f"Applicant is {profile['age']} years old, residing in {rural_str}. "
        f"Reported monthly income: Rs. {profile['income']}. "
        f"Housing status: {housing_str}. "
        f"Applicant {caste_str}. "
        f"[STUB — replace with SRA Annexure-II format]"
    )


def _control_note_mr(profile: dict) -> str:
    """Marathi stub — must be verified by domain-familiar speaker before pilot."""
    rural_str   = "ग्रामीण भागात" if profile["rural"] else "शहरी भागात"
    caste_str   = "मागासवर्गीय प्रवर्गातील" if profile["caste_marginalized"] else "सामान्य प्रवर्गातील"
    housing_str = profile.get("housing_status", "अज्ञात")
    return (
        f"अर्जदाराचे वय {profile['age']} वर्षे आहे, {rural_str} राहतात. "
        f"मासिक उत्पन्न: रु. {profile['income']}. "
        f"निवास स्थिती: {housing_str}. "
        f"अर्जदार {caste_str} आहे. "
        f"[STUB — SRA अनुलग्नक-II स्वरूपात बदलणे आवश्यक]"
    )


# Treatment signals — one per note, subtle and naturalistic (TDD §7.2).
# These are illustrative stubs; actual signals pending SRA format guidance.
TREATMENT_SIGNALS_EN = [
    "Applicant arrived at kiosk by personal vehicle.",
    "Applicant mentioned children attend private school.",
    "Applicant wearing gold jewellery at time of visit.",
    "Household reported owning a refrigerator and television.",
    "Applicant's spouse reported working in private sector.",
    "Applicant mentioned recent home renovation.",
    "Children's school fees noted as above government school rates.",
    "Applicant owns a mobile phone with active data plan.",
]

TREATMENT_SIGNALS_MR = [
    "अर्जदार स्वतःच्या वाहनाने कियोस्कवर आले.",
    "अर्जदाराने मुले खाजगी शाळेत जातात असे नमूद केले.",
    "भेटीच्या वेळी अर्जदाराने सोन्याचे दागिने घातले होते.",
    "घरात रेफ्रिजरेटर आणि टेलिव्हिजन असल्याचे नोंदवले.",
    "अर्जदाराचे पती/पत्नी खाजगी क्षेत्रात काम करतात.",
    "अर्जदाराने अलीकडील घराची दुरुस्ती नमूद केली.",
    "मुलांची शाळा फी सरकारी शाळेच्या दरापेक्षा जास्त नोंदवली.",
    "अर्जदाराकडे सक्रिय डेटा प्लॅनसह मोबाइल फोन आहे.",
]


def _treatment_note_en(profile: dict, signal: str) -> str:
    """
    Signal-injected note: identical structure to control + one unencoded signal.
    Critical constraint: only difference is the injected signal (TDD §7.2).
    """
    rural_str   = "rural area" if profile["rural"] else "urban area"
    caste_str   = "belongs to marginalized caste category" if profile["caste_marginalized"] else "general category"
    housing_str = profile.get("housing_status", "unknown")
    return (
        f"Applicant is {profile['age']} years old, residing in {rural_str}. "
        f"Reported monthly income: Rs. {profile['income']}. "
        f"Housing status: {housing_str}. "
        f"Applicant {caste_str}. "
        f"{signal} "
        f"[STUB — replace with SRA Annexure-II format]"
    )


def _treatment_note_mr(profile: dict, signal_mr: str) -> str:
    """Marathi stub — must be verified by domain-familiar speaker before pilot."""
    rural_str   = "ग्रामीण भागात" if profile["rural"] else "शहरी भागात"
    caste_str   = "मागासवर्गीय प्रवर्गातील" if profile["caste_marginalized"] else "सामान्य प्रवर्गातील"
    housing_str = profile.get("housing_status", "अज्ञात")
    return (
        f"अर्जदाराचे वय {profile['age']} वर्षे आहे, {rural_str} राहतात. "
        f"मासिक उत्पन्न: रु. {profile['income']}. "
        f"निवास स्थिती: {housing_str}. "
        f"अर्जदार {caste_str} आहे. "
        f"{signal_mr} "
        f"[STUB — SRA अनुलग्नक-II स्वरूपात बदलणे आवश्यक]"
    )


# ── Rule result assignment ────────────────────────────────────────────────────
def _rule_result(algo_rec: AlgoRecommendationEnum) -> RuleResultEnum:
    """
    Stub rule result: broadly consistent with algo recommendation.
    Approve cases lean ELIGIBLE, reject cases lean INELIGIBLE.
    Some approved cases are INELIGIBLE (tests aversion in both directions).
    """
    if algo_rec == AlgoRecommendationEnum.APPROVE:
        return RNG.choice([
            RuleResultEnum.ELIGIBLE_BY_RULE,
            RuleResultEnum.ELIGIBLE_BY_RULE,
            RuleResultEnum.INELIGIBLE_BY_RULE,  # 1 in 3: approve despite rule fail
        ])
    else:
        return RNG.choice([
            RuleResultEnum.INELIGIBLE_BY_RULE,
            RuleResultEnum.INELIGIBLE_BY_RULE,
            RuleResultEnum.ELIGIBLE_BY_RULE,    # 1 in 3: reject despite rule pass
        ])


# ── Main seeder ───────────────────────────────────────────────────────────────
def seed(clear: bool = False) -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        existing = db.query(Vignette).count()

        if clear:
            db.query(Vignette).delete()
            db.commit()
            print(f"Cleared {existing} existing vignettes.")
            existing = 0
        elif existing > 0:
            print(
                f"Pool already contains {existing} vignettes. "
                "Use --clear to reseed. Exiting."
            )
            return

        created = 0
        # 4 buckets × 80 = 320
        buckets: list[tuple[ArmEnum, AlgoRecommendationEnum]] = [
            (ArmEnum.CONTROL,   AlgoRecommendationEnum.APPROVE),
            (ArmEnum.CONTROL,   AlgoRecommendationEnum.REJECT),
            (ArmEnum.TREATMENT, AlgoRecommendationEnum.APPROVE),
            (ArmEnum.TREATMENT, AlgoRecommendationEnum.REJECT),
        ]

        signal_cycle_en = list(TREATMENT_SIGNALS_EN)
        signal_cycle_mr = list(TREATMENT_SIGNALS_MR)

        for arm, algo_rec in buckets:
            for i in range(80):
                profile = _make_profile()
                rr      = _rule_result(algo_rec)

                if arm == ArmEnum.CONTROL:
                    note_en = _control_note_en(profile)
                    note_mr = _control_note_mr(profile)
                else:
                    # Cycle through signals evenly across the 80 treatment cases
                    signal_en = signal_cycle_en[i % len(signal_cycle_en)]
                    signal_mr = signal_cycle_mr[i % len(signal_cycle_mr)]
                    note_en   = _treatment_note_en(profile, signal_en)
                    note_mr   = _treatment_note_mr(profile, signal_mr)

                v = Vignette(
                    arm                 = arm,
                    algo_recommendation = algo_rec,
                    rule_result         = rr,
                    profile_data        = profile,
                    field_note_en       = note_en,
                    field_note_mr       = note_mr,
                    pool_version        = POOL_VERSION,
                    used_count          = 0,
                )
                db.add(v)
                created += 1

        db.commit()
        print(f"Seeded {created} vignettes (pool_version={POOL_VERSION}).")
        print("NOTE: Field notes are stubs. Replace with SRA Annexure-II format before pilot.")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed SARAL v2 vignette pool")
    parser.add_argument(
        "--clear", action="store_true",
        help="Drop existing vignettes before seeding"
    )
    args = parser.parse_args()
    seed(clear=args.clear)