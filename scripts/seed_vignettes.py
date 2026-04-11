# scripts/seed_vignettes.py
"""
Vignette seeder for SARAL v2 — Tuesday pre-pilot version.
Generates 320 synthetic cases: 80 × (control/approve, control/reject,
                                     treatment/approve, treatment/reject).

Field records mimic SRA Annexure-II column structure.
Officer Remarks: control = thin/neutral, treatment = signal-bearing.

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

# ── Reproducible pool ─────────────────────────────────────────────────────────
SEED         = 42
RNG          = random.Random(SEED)
POOL_VERSION = "v2.0-tuesday"

# ── Profile values (SRA Annexure-II column logic) ─────────────────────────────
ELECTORAL_ROLL_YEARS = [1995, 1998, 2000, 2002, 2004, 2005, 2007, 2008, 2010]
STRUCTURE_TYPES      = ["R", "R/C", "C"]
CARPET_AREAS         = [110, 140, 160, 175, 180, 195, 200, 210, 225]
PRE_1995_OPTIONS     = ["Yes", "No"]
CONSENT_OPTIONS      = ["Yes", "No"]


def _make_profile() -> dict:
    """
    Operator sees the 5 SRA sheet columns via the Field Record.
    Backend-only covariates retained for heterogeneity analysis.
    """
    return {
        # Operator-visible (served via field record display)
        "electoral_roll_year": RNG.choice(ELECTORAL_ROLL_YEARS),
        "structure_type":      RNG.choice(STRUCTURE_TYPES),
        "carpet_area_sqft":    RNG.choice(CARPET_AREAS),
        "pre_1995_evidence":   RNG.choice(PRE_1995_OPTIONS),
        "consent":             RNG.choice(CONSENT_OPTIONS),
        # Backend-only
        "age":                RNG.randint(21, 65),
        "income":             RNG.choice([2000, 3500, 4200, 5000, 6500, 7800, 9000, 10500]),
        "income_period":      "monthly",
        "caste_marginalized": RNG.choice([0, 1]),
    }


# ── Field record builders ─────────────────────────────────────────────────────
# Field Record (formal columns) + Officer Remark stored together in field_note_en/mr.
# UI splits on "Field Remark :" at render time.
# Structure is identical across arms — only the remark content differs (TDD §7.2).

def _field_record_en(profile: dict, remark: str) -> str:
    return (
        f"Electoral Roll Year : {profile['electoral_roll_year']}\n"
        f"Structure Type      : {profile['structure_type']}\n"
        f"Carpet Area         : {profile['carpet_area_sqft']} sq ft\n"
        f"Pre-1995 Evidence   : {profile['pre_1995_evidence']}\n"
        f"Consent             : {profile['consent']}\n"
        f"Field Remark        : {remark}"
    )


def _field_record_mr(profile: dict, remark: str) -> str:
    return (
        f"मतदार यादी वर्ष     : {profile['electoral_roll_year']}\n"
        f"संरचना प्रकार       : {profile['structure_type']}\n"
        f"कार्पेट क्षेत्र      : {profile['carpet_area_sqft']} चौ.फू.\n"
        f"१९९५ पूर्व पुरावा    : {profile['pre_1995_evidence']}\n"
        f"संमती               : {profile['consent']}\n"
        f"क्षेत्र निरीक्षण      : {remark}"
    )


# ── Officer Remarks ───────────────────────────────────────────────────────────
# Control: thin, neutral, non-diagnostic.
# Not blank — "presence of remark" must not become the treatment signal.

CONTROL_REMARKS_EN = [
    "Visited site; resident present.",
    "Structure seen, basic details checked.",
    "Occupancy confirmed at site.",
]

CONTROL_REMARKS_MR = [
    "साइटला भेट; रहिवासी उपस्थित.",
    "संरचना पाहिली; तपशील तपासले.",
    "राहण्याची खात्री झाली.",
]

# Treatment: short, fragmented, observational, slightly subjective.
# 6 signal types × 2 variants = 12 entries. Descriptive not interpretive.
# Index alignment: EN[i] ↔ MR[i] for every i.
#
#  0-1 : vehicle / mobility
#  2-3 : private school
#  4-5 : jewellery / appearance
#  6-7 : appliances / assets
#  8-9 : renovation / housing quality
# 10-11: financial stability (neighbour signal)

TREATMENT_REMARKS_EN = [
    # 0-1: vehicle
    "Own bike seen outside.",
    "Came on two-wheeler; vehicle parked.",
    # 2-3: school
    "Children in private school, fees high.",
    "Private school mentioned, not govt.",
    # 4-5: jewellery
    "Gold chain, rings visible — looks above average.",
    "Dressed well, wearing gold — not typical.",
    # 6-7: appliances
    "TV, fridge inside.",
    "Appliances present — TV, fridge seen.",
    # 8-9: renovation
    "Fresh paint, tiles — house recently done.",
    "Looks newly done, better than nearby.",
    # 10-11: neighbour signal
    "Neighbours say income steady.",
    "Local says financially ok.",
]

TREATMENT_REMARKS_MR = [
    # 0-1: vehicle
    "दुचाकी बाहेर दिसली.",
    "दुचाकीने आले; वाहन पार्क केलेले.",
    # 2-3: school
    "मुलं खाजगी शाळेत; फी जास्त.",
    "खाजगी शाळा सांगितली; सरकारी नाही.",
    # 4-5: jewellery
    "सोन्याची चैन, अंगठ्या दिसल्या — सरासरीपेक्षा वर.",
    "चांगले कपडे, सोने घातलेले — सामान्य नाही.",
    # 6-7: appliances
    "टीव्ही, फ्रिज आत दिसले.",
    "घरात उपकरणे — टीव्ही, फ्रिज.",
    # 8-9: renovation
    "नवीन रंग, टाइल्स — घर अलीकडे केलेले.",
    "घर नवीनसारखे; आसपासपेक्षा चांगले.",
    # 10-11: neighbour signal
    "शेजारी म्हणतात उत्पन्न स्थिर.",
    "स्थानिक म्हणतात आर्थिक स्थिती ठीक.",
]


def _control_remark(rng: random.Random, locale: str) -> str:
    pool = CONTROL_REMARKS_MR if locale == "mr" else CONTROL_REMARKS_EN
    return rng.choice(pool)


def _treatment_remark(rng: random.Random, locale: str, case_idx: int) -> str:
    """
    Cycles through 6 signal types (2 variants each) across 80 treatment cases.
    case_idx mod 6 selects signal type; rng picks one of the 2 variants.
    """
    pool = TREATMENT_REMARKS_MR if locale == "mr" else TREATMENT_REMARKS_EN
    base = (case_idx % 6) * 2
    return rng.choice(pool[base:base + 2])


# ── Rule result assignment ────────────────────────────────────────────────────
def _rule_result(algo_rec: AlgoRecommendationEnum) -> RuleResultEnum:
    """
    Broadly consistent with algo recommendation but not perfectly correlated.
    1 in 3 approve cases fail the rule; 1 in 3 reject cases pass it.
    Tests aversion in both directions (TDD §5.3).
    """
    if algo_rec == AlgoRecommendationEnum.APPROVE:
        return RNG.choice([
            RuleResultEnum.ELIGIBLE_BY_RULE,
            RuleResultEnum.ELIGIBLE_BY_RULE,
            RuleResultEnum.INELIGIBLE_BY_RULE,
        ])
    else:
        return RNG.choice([
            RuleResultEnum.INELIGIBLE_BY_RULE,
            RuleResultEnum.INELIGIBLE_BY_RULE,
            RuleResultEnum.ELIGIBLE_BY_RULE,
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
        buckets: list[tuple[ArmEnum, AlgoRecommendationEnum]] = [
            (ArmEnum.CONTROL,   AlgoRecommendationEnum.APPROVE),
            (ArmEnum.CONTROL,   AlgoRecommendationEnum.REJECT),
            (ArmEnum.TREATMENT, AlgoRecommendationEnum.APPROVE),
            (ArmEnum.TREATMENT, AlgoRecommendationEnum.REJECT),
        ]

        for arm, algo_rec in buckets:
            for i in range(80):
                profile = _make_profile()
                rr      = _rule_result(algo_rec)

                if arm == ArmEnum.CONTROL:
                    note_en = _field_record_en(profile, _control_remark(RNG, "en"))
                    note_mr = _field_record_mr(profile, _control_remark(RNG, "mr"))
                else:
                    note_en = _field_record_en(profile, _treatment_remark(RNG, "en", i))
                    note_mr = _field_record_mr(profile, _treatment_remark(RNG, "mr", i))

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
        print("NOTE: Stub remarks — replace with verified SRA format before real pilot.")

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