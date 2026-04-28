# scripts/seed_vignettes.py
"""
Vignette seeder for SARAL v2 Phase 2 — Mumbai pilot (final-officer framing).

Design (v2.4):
  16 profiles × 2 arm versions = 32 vignette objects.
  Each operator draws 12 profile_ids from 16 at session time.
  Within those 12, 6 are randomly assigned control, 6 treatment.
  No List A/B coupling — assignment is fully randomised at draw.

  Rule logic is MULTI-FACTOR:
    eligible   = pre_cutoff_status == Yes AND carpet_area <= 200 AND income == low
    ineligible = any of those conditions violated
    Some borderline cases have mixed signals (e.g. pre_cutoff Yes but carpet > 200)
    to prevent operators from learning a single-field rule.

  Treatment signals ADD information beyond the structured record.
  They are observations, history, or third-party statements — never redundant
  restatements of what the structured fields already show.

  Signal direction is coded and LOCKED. Do not modify after seeding.

  Cell distribution:
    APPROVE + WITH:    profiles 3, 4, 10, 15, 16    (5)
    APPROVE + AGAINST: profiles 7, 8, 13, 14        (4)
    REJECT  + WITH:    profiles 1, 2, 5, 11, 12     (5)
    REJECT  + AGAINST: profiles 6, 9                 (2)

Usage:
    python -m scripts.seed_vignettes          # seed
    python -m scripts.seed_vignettes --clear  # drop and reseed
"""
from __future__ import annotations

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal, engine
from app.models import (
    Base, ArmEnum, AlgoRecommendationEnum, RuleResultEnum, Vignette,
)

POOL_VERSION = "v2.4-mumbai-final"

# ─────────────────────────────────────────────────────────────────────────────
# RULE LOGIC (documented, multi-factor)
#
# Eligible if ALL of:
#   - pre_cutoff_status == "Yes"
#   - carpet_area_sqft <= 200
#   - declared_income_band == "low"
#
# Ineligible if ANY of:
#   - pre_cutoff_status == "No"
#   - carpet_area_sqft > 200
#   - declared_income_band != "low"
#
# IMPORTANT: Some profiles are deliberately borderline — they meet 2 of 3
# criteria but fail on 1. This prevents operators from learning a single-field
# heuristic. The algo recommendation reflects the overall rule output.
#
# Document completeness is distributed across BOTH arms — some APPROVE cases
# have sparse docs (genuine eligibility, paperwork gaps), some REJECT cases
# have full docs (fully documented but ineligible).
# ─────────────────────────────────────────────────────────────────────────────

PROFILES = [

    # ══════════════════════════════════════════════════════════════════════════
    # A. PAKKA-HOUSE STATUS (profiles 1-4)
    # ══════════════════════════════════════════════════════════════════════════

    # ── Profile 1 — REJECT + WITH ────────────────────────────────────────────
    # Structured: pakka, large area, no pre-cutoff → clearly ineligible
    # Signal ADDS: behavioural observation (applicant admitted to owning house)
    {
        "profile_id": 1,
        "category": "pakka_house_status",
        "algo_recommendation": "reject",
        "rule_result": "INELIGIBLE_BY_RULE",
        "signal_direction": "WITH",
        "profile": {
            "electoral_roll_year": 2010,
            "structure_type": "pakka",
            "carpet_area_sqft": 225,
            "pre_cutoff_status": "No",
            "documents": ["Aadhaar", "Electoral roll", "Income certificate"],
            "declared_income_band": "medium",
            "household_size": 3,
        },
        "control_note_en": "Field visit: occupancy confirmed at registered address; routine check completed.",
        "control_note_mr": "क्षेत्रभेट: नोंदणीकृत पत्त्यावर वास्तव्य पुष्टी; नियमित तपासणी पूर्ण.",
        "treatment_note_en": "Field visit: applicant admitted to owning the house during conversation; neighbours confirmed long-term residence.",
        "treatment_note_mr": "क्षेत्रभेट: अर्जदाराने संभाषणात घर स्वतःचे असल्याचे मान्य केले; शेजाऱ्यांनी दीर्घकालीन वास्तव्य पुष्टी केली.",
    },

    # ── Profile 2 — REJECT + WITH ────────────────────────────────────────────
    # Structured: semi but large area, no pre-cutoff, medium income → ineligible
    # Signal ADDS: history (prior PMAY allocation — not in structured record)
    {
        "profile_id": 2,
        "category": "pakka_house_status",
        "algo_recommendation": "reject",
        "rule_result": "INELIGIBLE_BY_RULE",
        "signal_direction": "WITH",
        "profile": {
            "electoral_roll_year": 2011,
            "structure_type": "semi",
            "carpet_area_sqft": 210,
            "pre_cutoff_status": "No",
            "documents": ["Aadhaar", "Electoral roll"],
            "declared_income_band": "medium",
            "household_size": 2,
        },
        "control_note_en": "Verification: site check done; resident available during visit.",
        "control_note_mr": "सत्यापन: क्षेत्र तपासणी पूर्ण; भेटीदरम्यान रहिवासी उपलब्ध.",
        "treatment_note_en": "Field visit: applicant received pakka house through prior PMAY allocation per ward records.",
        "treatment_note_mr": "क्षेत्रभेट: वॉर्ड नोंदीनुसार अर्जदाराला पूर्वीच्या PMAY वाटपातून पक्के घर मिळाले.",
    },

    # ── Profile 3 — APPROVE + WITH ───────────────────────────────────────────
    # Structured: kuccha, small area, pre-cutoff yes, low income → eligible
    # Signal ADDS: observation (no pakka house, rents — not in structured record)
    {
        "profile_id": 3,
        "category": "pakka_house_status",
        "algo_recommendation": "approve",
        "rule_result": "ELIGIBLE_BY_RULE",
        "signal_direction": "WITH",
        "profile": {
            "electoral_roll_year": 2002,
            "structure_type": "kuccha",
            "carpet_area_sqft": 150,
            "pre_cutoff_status": "Yes",
            "documents": ["Aadhaar", "Ration card"],
            "declared_income_band": "low",
            "household_size": 5,
        },
        "control_note_en": "Field visit: structure observed; resident confirmed at site.",
        "control_note_mr": "क्षेत्रभेट: संरचना पाहिली; क्षेत्रात रहिवासी पुष्टी.",
        "treatment_note_en": "Field visit: no pakka house anywhere; applicant rents current dwelling from a relative.",
        "treatment_note_mr": "क्षेत्रभेट: कुठेही पक्के घर नाही; अर्जदार नातेवाईकांकडून सध्याचे निवासस्थान भाड्याने घेतो.",
    },

    # ── Profile 4 — APPROVE + WITH ───────────────────────────────────────────
    # Structured: kuccha, small, pre-cutoff yes → eligible; sparse docs
    # Signal ADDS: observation (chawl, shared facilities — context not in record)
    {
        "profile_id": 4,
        "category": "pakka_house_status",
        "algo_recommendation": "approve",
        "rule_result": "ELIGIBLE_BY_RULE",
        "signal_direction": "WITH",
        "profile": {
            "electoral_roll_year": 1998,
            "structure_type": "kuccha",
            "carpet_area_sqft": 140,
            "pre_cutoff_status": "Yes",
            "documents": ["Aadhaar", "Electoral roll"],
            "declared_income_band": "low",
            "household_size": 4,
        },
        "control_note_en": "Verification: standard check completed; documentation submitted.",
        "control_note_mr": "सत्यापन: नियमित तपासणी पूर्ण; कागदपत्रे सादर.",
        "treatment_note_en": "Field visit: applicant lives in chawl with shared toilet and water; no individual home observed.",
        "treatment_note_mr": "क्षेत्रभेट: अर्जदार सामायिक शौचालय व पाण्यासह चाळीत राहतो; वैयक्तिक घर दिसले नाही.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # B. FAMILY PROPERTY (profiles 5-8)
    # ══════════════════════════════════════════════════════════════════════════

    # ── Profile 5 — REJECT + WITH ────────────────────────────────────────────
    # Structured: borderline (pre-cutoff No, semi, medium) → ineligible
    # Signal ADDS: third-party info (neighbours say father transferred property)
    {
        "profile_id": 5,
        "category": "family_property",
        "algo_recommendation": "reject",
        "rule_result": "INELIGIBLE_BY_RULE",
        "signal_direction": "WITH",
        "profile": {
            "electoral_roll_year": 2012,
            "structure_type": "semi",
            "carpet_area_sqft": 200,
            "pre_cutoff_status": "No",
            "documents": ["Aadhaar", "Electoral roll", "Bank statement"],
            "declared_income_band": "medium",
            "household_size": 3,
        },
        "control_note_en": "Field visit: occupancy verified; basic details confirmed at site.",
        "control_note_mr": "क्षेत्रभेट: वास्तव्य सत्यापित; मूलभूत तपशील क्षेत्रात पुष्टी.",
        "treatment_note_en": "Verification: neighbours say father recently transferred property to applicant's name.",
        "treatment_note_mr": "सत्यापन: शेजाऱ्यांच्या म्हणण्यानुसार वडिलांनी अलीकडे मालमत्ता अर्जदाराच्या नावावर हस्तांतरित केली.",
    },

    # ── Profile 6 — REJECT + AGAINST ─────────────────────────────────────────
    # Structured: borderline (pre-cutoff No, semi) → ineligible by rule
    # Signal ADDS: suggests applicant is genuinely without assets — pushes AGAINST rejection
    {
        "profile_id": 6,
        "category": "family_property",
        "algo_recommendation": "reject",
        "rule_result": "INELIGIBLE_BY_RULE",
        "signal_direction": "AGAINST",
        "profile": {
            "electoral_roll_year": 2009,
            "structure_type": "semi",
            "carpet_area_sqft": 195,
            "pre_cutoff_status": "No",
            "documents": ["Aadhaar", "Income certificate"],
            "declared_income_band": "medium",
            "household_size": 4,
        },
        "control_note_en": "Verification: site check complete; resident present during visit.",
        "control_note_mr": "सत्यापन: क्षेत्र तपासणी पूर्ण; भेटीदरम्यान रहिवासी उपस्थित.",
        "treatment_note_en": "Field visit: applicant lives in separate household; no inherited property access; supports family on own income.",
        "treatment_note_mr": "क्षेत्रभेट: अर्जदार वेगळ्या घरात राहतो; वारसा मालमत्तेचा प्रवेश नाही; स्वतःच्या उत्पन्नावर कुटुंबाचा उदरनिर्वाह.",
    },

    # ── Profile 7 — APPROVE + AGAINST ────────────────────────────────────────
    # Structured: eligible (pre-cutoff Yes, kuccha, small, low income)
    # Signal ADDS: family context that casts doubt (family has city house)
    {
        "profile_id": 7,
        "category": "family_property",
        "algo_recommendation": "approve",
        "rule_result": "ELIGIBLE_BY_RULE",
        "signal_direction": "AGAINST",
        "profile": {
            "electoral_roll_year": 2005,
            "structure_type": "kuccha",
            "carpet_area_sqft": 175,
            "pre_cutoff_status": "Yes",
            "documents": ["Aadhaar", "Electoral roll", "Bank statement"],
            "declared_income_band": "low",
            "household_size": 3,
        },
        "control_note_en": "Field visit: documentation reviewed; no discrepancies noted.",
        "control_note_mr": "क्षेत्रभेट: कागदपत्रे तपासली; विसंगती नाही.",
        "treatment_note_en": "Field visit: family owns a flat in Thane; applicant claims to live separately but address overlaps.",
        "treatment_note_mr": "क्षेत्रभेट: कुटुंबाचा ठाण्यात फ्लॅट आहे; अर्जदार वेगळे राहत असल्याचे सांगतो पण पत्ता ओव्हरलॅप होतो.",
    },

    # ── Profile 8 — APPROVE + AGAINST ────────────────────────────────────────
    # Structured: eligible (pre-cutoff Yes, kuccha, low income)
    # Signal ADDS: family land context that raises questions
    {
        "profile_id": 8,
        "category": "family_property",
        "algo_recommendation": "approve",
        "rule_result": "ELIGIBLE_BY_RULE",
        "signal_direction": "AGAINST",
        "profile": {
            "electoral_roll_year": 2004,
            "structure_type": "kuccha",
            "carpet_area_sqft": 180,
            "pre_cutoff_status": "Yes",
            "documents": ["Aadhaar", "Electoral roll", "Income certificate"],
            "declared_income_band": "low",
            "household_size": 6,
        },
        "control_note_en": "Verification: records checked and filed; standard process.",
        "control_note_mr": "सत्यापन: नोंदी तपासून दाखल; नियमित प्रक्रिया.",
        "treatment_note_en": "Field visit: father has agriculture land in village; applicant has kacha house but family is not landless.",
        "treatment_note_mr": "क्षेत्रभेट: वडिलांची गावात शेतजमीन; अर्जदाराचे कच्चे घर आहे पण कुटुंब भूमिहीन नाही.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # C. TENANCY / OCCUPANCY (profiles 9-10)
    # ══════════════════════════════════════════════════════════════════════════

    # ── Profile 9 — REJECT + AGAINST ─────────────────────────────────────────
    # Structured: ineligible (no pre-cutoff, semi, medium)
    # Signal ADDS: sympathy context — large needy family, junior officer flagged
    {
        "profile_id": 9,
        "category": "tenancy_occupancy",
        "algo_recommendation": "reject",
        "rule_result": "INELIGIBLE_BY_RULE",
        "signal_direction": "AGAINST",
        "profile": {
            "electoral_roll_year": 2010,
            "structure_type": "semi",
            "carpet_area_sqft": 185,
            "pre_cutoff_status": "No",
            "documents": ["Aadhaar", "Electoral roll", "Ration card"],
            "declared_income_band": "medium",
            "household_size": 7,
        },
        "control_note_en": "Field visit: resident available at premises; routine verification.",
        "control_note_mr": "क्षेत्रभेट: रहिवासी परिसरात उपलब्ध; नियमित सत्यापन.",
        "treatment_note_en": "Field visit: tenant on rent; large family of 7; junior officer noted family appears genuinely in need of housing.",
        "treatment_note_mr": "क्षेत्रभेट: भाड्याने राहतो; ७ जणांचे मोठे कुटुंब; कनिष्ठ अधिकाऱ्याने कुटुंबाला खरोखर घराची गरज असल्याचे नोंदवले.",
    },

    # ── Profile 10 — APPROVE + WITH ──────────────────────────────────────────
    # Structured: eligible (pre-cutoff Yes, kuccha, low income)
    # Signal ADDS: tenancy context supporting need (uncertain SRA status)
    {
        "profile_id": 10,
        "category": "tenancy_occupancy",
        "algo_recommendation": "approve",
        "rule_result": "ELIGIBLE_BY_RULE",
        "signal_direction": "WITH",
        "profile": {
            "electoral_roll_year": 2000,
            "structure_type": "kuccha",
            "carpet_area_sqft": 160,
            "pre_cutoff_status": "Yes",
            "documents": ["Aadhaar", "Electoral roll"],
            "declared_income_band": "low",
            "household_size": 4,
        },
        "control_note_en": "Verification: occupancy confirmed; documents on file.",
        "control_note_mr": "सत्यापन: वास्तव्य पुष्टी; कागदपत्रे दाखल.",
        "treatment_note_en": "Field visit: lives on rent; has been waiting for SRA allocation; uncertain about process.",
        "treatment_note_mr": "क्षेत्रभेट: भाड्याने राहतो; SRA वाटपाची वाट पाहत आहे; प्रक्रियेबद्दल अनिश्चित.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # D. VISIBLE AFFLUENCE (profiles 11-12)
    # ══════════════════════════════════════════════════════════════════════════

    # ── Profile 11 — REJECT + WITH ───────────────────────────────────────────
    # Structured: borderline (pre-cutoff No, carpet 190, medium income)
    # Signal ADDS: behavioural observation (lifestyle inconsistency not visible in record)
    {
        "profile_id": 11,
        "category": "visible_affluence",
        "algo_recommendation": "reject",
        "rule_result": "INELIGIBLE_BY_RULE",
        "signal_direction": "WITH",
        "profile": {
            "electoral_roll_year": 2010,
            "structure_type": "semi",
            "carpet_area_sqft": 190,
            "pre_cutoff_status": "No",
            "documents": ["Aadhaar", "Electoral roll", "Income certificate"],
            "declared_income_band": "medium",
            "household_size": 3,
        },
        "control_note_en": "Field visit: resident present; standard details collected.",
        "control_note_mr": "क्षेत्रभेट: रहिवासी उपस्थित; नियमित तपशील गोळा केले.",
        "treatment_note_en": "Field visit: applicant arrived in private car; gold jewellery observed; lifestyle appears above declared income.",
        "treatment_note_mr": "क्षेत्रभेट: अर्जदार खाजगी गाडीने आला; सोन्याचे दागिने दिसले; जीवनशैली जाहीर उत्पन्नापेक्षा वर दिसते.",
    },

    # ── Profile 12 — REJECT + WITH ───────────────────────────────────────────
    # Structured: ineligible (no pre-cutoff, carpet 205, medium)
    # Signal ADDS: third-party info (shopkeeper says applicant has business income)
    {
        "profile_id": 12,
        "category": "visible_affluence",
        "algo_recommendation": "reject",
        "rule_result": "INELIGIBLE_BY_RULE",
        "signal_direction": "WITH",
        "profile": {
            "electoral_roll_year": 2013,
            "structure_type": "semi",
            "carpet_area_sqft": 205,
            "pre_cutoff_status": "No",
            "documents": ["Aadhaar", "Electoral roll"],
            "declared_income_band": "medium",
            "household_size": 2,
        },
        "control_note_en": "Verification: visit completed; basic details verified on site.",
        "control_note_mr": "सत्यापन: भेट पूर्ण; मूलभूत तपशील क्षेत्रात सत्यापित.",
        "treatment_note_en": "Verification: local shopkeeper says applicant runs a side business; income may be higher than declared.",
        "treatment_note_mr": "सत्यापन: स्थानिक दुकानदार म्हणतो अर्जदार साइड बिझनेस चालवतो; उत्पन्न जाहीर केलेल्यापेक्षा जास्त असू शकते.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # E. DOCUMENTATION (profiles 13-14)
    # ══════════════════════════════════════════════════════════════════════════

    # ── Profile 13 — APPROVE + AGAINST ───────────────────────────────────────
    # Structured: eligible (pre-cutoff Yes, semi, small, low income, full docs)
    # Signal ADDS: history (prior rejection — not in structured record)
    {
        "profile_id": 13,
        "category": "documentation",
        "algo_recommendation": "approve",
        "rule_result": "ELIGIBLE_BY_RULE",
        "signal_direction": "AGAINST",
        "profile": {
            "electoral_roll_year": 2008,
            "structure_type": "semi",
            "carpet_area_sqft": 170,
            "pre_cutoff_status": "Yes",
            "documents": ["Aadhaar", "Electoral roll", "Income certificate"],
            "declared_income_band": "low",
            "household_size": 5,
        },
        "control_note_en": "Field visit: documentation in order; all records collected.",
        "control_note_mr": "क्षेत्रभेट: कागदपत्रे व्यवस्थित; सर्व नोंदी गोळा केल्या.",
        "treatment_note_en": "Records: previous application was rejected last year for data mismatch; applicant has resubmitted with same documents.",
        "treatment_note_mr": "अभिलेख: गेल्या वर्षीचा अर्ज डेटा विसंगतीमुळे नाकारला; अर्जदाराने त्याच कागदपत्रांसह पुन्हा सादर केला.",
    },

    # ── Profile 14 — APPROVE + AGAINST ───────────────────────────────────────
    # Structured: eligible (pre-cutoff Yes, kuccha, small, low income)
    # Signal ADDS: officer observation about document quality (not in record)
    {
        "profile_id": 14,
        "category": "documentation",
        "algo_recommendation": "approve",
        "rule_result": "ELIGIBLE_BY_RULE",
        "signal_direction": "AGAINST",
        "profile": {
            "electoral_roll_year": 2002,
            "structure_type": "kuccha",
            "carpet_area_sqft": 145,
            "pre_cutoff_status": "Yes",
            "documents": ["Aadhaar", "Income certificate"],
            "declared_income_band": "low",
            "household_size": 4,
        },
        "control_note_en": "Verification: documents reviewed; application details confirmed.",
        "control_note_mr": "सत्यापन: कागदपत्रे तपासली; अर्ज तपशील पुष्टी.",
        "treatment_note_en": "Verification: income certificate appears recently issued; junior officer noted values don't match older records on file.",
        "treatment_note_mr": "सत्यापन: उत्पन्न प्रमाणपत्र अलीकडे जारी केल्यासारखे दिसते; कनिष्ठ अधिकाऱ्याने नोंदवले की आकडे जुन्या नोंदींशी जुळत नाहीत.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # F. SYMPATHY FRAMING (profiles 15-16)
    # ══════════════════════════════════════════════════════════════════════════

    # ── Profile 15 — APPROVE + WITH ──────────────────────────────────────────
    # Structured: eligible (pre-cutoff Yes, kuccha, very small, low income)
    # Signal ADDS: emotional context (prior rejection, distrust — not in record)
    {
        "profile_id": 15,
        "category": "sympathy_framing",
        "algo_recommendation": "approve",
        "rule_result": "ELIGIBLE_BY_RULE",
        "signal_direction": "WITH",
        "profile": {
            "electoral_roll_year": 2000,
            "structure_type": "kuccha",
            "carpet_area_sqft": 130,
            "pre_cutoff_status": "Yes",
            "documents": ["Aadhaar", "Electoral roll", "Ration card"],
            "declared_income_band": "low",
            "household_size": 6,
        },
        "control_note_en": "Field visit: resident at home; records collected without issues.",
        "control_note_mr": "क्षेत्रभेट: रहिवासी घरी; नोंदी अडचणीशिवाय गोळा केल्या.",
        "treatment_note_en": "Field visit: applicant expressed frustration with process; has been rejected twice before; says family desperately needs permanent housing.",
        "treatment_note_mr": "क्षेत्रभेट: अर्जदाराने प्रक्रियेबद्दल नाराजी व्यक्त केली; यापूर्वी दोनदा नाकारले; कुटुंबाला कायमस्वरूपी घराची तातडीने गरज असल्याचे सांगतो.",
    },

    # ── Profile 16 — APPROVE + WITH ──────────────────────────────────────────
    # Structured: eligible (pre-cutoff Yes, kuccha, low income); sparse docs
    # Signal ADDS: migration context (village ID, reports village home)
    {
        "profile_id": 16,
        "category": "sympathy_framing",
        "algo_recommendation": "approve",
        "rule_result": "ELIGIBLE_BY_RULE",
        "signal_direction": "WITH",
        "profile": {
            "electoral_roll_year": 2004,
            "structure_type": "kuccha",
            "carpet_area_sqft": 155,
            "pre_cutoff_status": "Yes",
            "documents": ["Aadhaar", "Electoral roll"],
            "declared_income_band": "low",
            "household_size": 3,
        },
        "control_note_en": "Verification: standard check done; no issues found.",
        "control_note_mr": "सत्यापन: नियमित तपासणी; कोणतीही समस्या नाही.",
        "treatment_note_en": "Verification: applicant migrated from village; holds village ID only; reports having no home in Mumbai.",
        "treatment_note_mr": "सत्यापन: अर्जदार गावातून स्थलांतरित; फक्त गावचे ओळखपत्र; मुंबईत घर नसल्याचे सांगतो.",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# SEEDER
#
# Creates 32 vignettes: 16 profiles × 2 arm versions (control + treatment).
# No List A/B coupling — session-time logic handles randomisation.
# Each vignette stores its profile_id but NOT a list assignment.
# ─────────────────────────────────────────────────────────────────────────────

def seed(clear: bool = False) -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        existing = db.query(Vignette).count()

        if clear:
            db.query(Vignette).delete()
            db.commit()
            print(f"Cleared {existing} existing vignettes.")
        elif existing > 0:
            print(f"Pool already contains {existing} vignettes. Use --clear to reseed.")
            return

        created = 0

        for p in PROFILES:
            pid = p["profile_id"]
            rec = (AlgoRecommendationEnum.APPROVE
                   if p["algo_recommendation"] == "approve"
                   else AlgoRecommendationEnum.REJECT)
            rule = (RuleResultEnum.ELIGIBLE_BY_RULE
                    if p["rule_result"] == "ELIGIBLE_BY_RULE"
                    else RuleResultEnum.INELIGIBLE_BY_RULE)

            for arm_str in ["control", "treatment"]:
                arm = ArmEnum.CONTROL if arm_str == "control" else ArmEnum.TREATMENT
                note_en = p["control_note_en"] if arm_str == "control" else p["treatment_note_en"]
                note_mr = p["control_note_mr"] if arm_str == "control" else p["treatment_note_mr"]

                v = Vignette(
                    arm                 = arm,
                    algo_recommendation = rec,
                    rule_result         = rule,
                    profile_data        = {
                        **p["profile"],
                        "signal_direction": p["signal_direction"],
                        "category":         p["category"],
                    },
                    field_note_en       = note_en,
                    field_note_mr       = note_mr,
                    pool_version        = POOL_VERSION,
                    pair_id             = pid,
                    list_assignment     = None,  # no list coupling
                    used_count          = 0,
                )
                db.add(v)
                created += 1

        db.commit()

        print(f"Seeded {created} vignettes (pool_version={POOL_VERSION}).")
        print()
        print("Pool structure:")
        print("  16 profiles × 2 arms = 32 vignette objects")
        print("  Session-time: draw 12 profile_ids from 16, assign 6 control + 6 treatment")
        print()
        print("Rule logic (multi-factor):")
        print("  Eligible:   pre_cutoff=Yes AND carpet<=200 AND income=low")
        print("  Ineligible: any condition violated")
        print()
        print("Signal direction distribution:")
        print("  APPROVE + WITH:    profiles 3, 4, 10, 15, 16    (5)")
        print("  APPROVE + AGAINST: profiles 7, 8, 13, 14        (4)")
        print("  REJECT  + WITH:    profiles 1, 2, 5, 11, 12     (5)")
        print("  REJECT  + AGAINST: profiles 6, 9                (2)")
        print()
        print("Document distribution:")
        docs_by_rec = {"approve": [], "reject": []}
        for p in PROFILES:
            docs_by_rec[p["algo_recommendation"]].append(len(p["profile"]["documents"]))
        for rec, counts in docs_by_rec.items():
            print(f"  {rec.upper()}: doc counts = {sorted(counts)} (mean={sum(counts)/len(counts):.1f})")
        print()
        print("Marathi translations require verification before pilot deployment.")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed SARAL v2 Phase 2 vignette pool")
    parser.add_argument("--clear", action="store_true", help="Drop existing vignettes before seeding")
    args = parser.parse_args()
    seed(clear=args.clear)