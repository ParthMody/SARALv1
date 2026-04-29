# scripts/seed_vignettes.py
"""
Vignette seeder for SARAL v2 Phase 2 — Mumbai pilot (v2.4-mumbai-final).

Grounded in: GR ZoPuDho-0810/Pr.Kr.96/2018/ZoPaSu-1

Design:
  16 profiles × 2 arm versions (control/treatment) = 32 vignette objects.
  Each operator draws 12 from 16, assigned 6 control + 6 treatment at session time.
  No List A/B coupling — fully randomised at draw.

  Signal direction LOCKED. Do not modify after seeding.

  Cell distribution (balanced 4×4):
    APPROVE + WITH:    profiles 3, 4, 10, 15     (4)
    APPROVE + AGAINST: profiles 7, 8, 13, 14     (4)
    REJECT  + WITH:    profiles 1, 2, 5, 11      (4)
    REJECT  + AGAINST: profiles 6, 9, 12, 16     (4)

  Rule logic (multi-factor, from 2018 GR):
    Eligible if ALL:
      - Structure existed on/before 1.1.2011 (mandatory proof from Vivaran Patra)
      - Current occupancy confirmed
      - Self-declaration: no other property
      - Aadhaar submitted
    Track B (post-2011 arrival): additionally needs notarized consent + OTC + extra proofs
    Disqualified if: D1 (family rehab), D2/D3 (non-independence), D4 (false declaration)

  All treatment signals paraphrased from:
    1. Phase 1 verification corpus (260 PMAY field observations, Maharashtra, 2026)
    2. GR-documented disqualifications (D1-D4, VP1-VP6, Track A/B)

  All PII is synthetic. No vignette corresponds to an identifiable person.

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
# 16 PROFILES — GR-grounded, signal direction locked
#
# Categories:
#   VP1/VP2 cutoff proof (1, 6, 12, 16)
#   Family disqualification D1/D2/D3 (2, 5)
#   Track A strong (3, 10)
#   Track B transfer (4, 9, 15)
#   Affluence / normative (7)
#   Self-declaration / property (8, 11)
#   Current occupancy (13)
#   Commercial misuse (14)
# ─────────────────────────────────────────────────────────────────────────────

PROFILES = [

    # ══════════════════════════════════════════════════════════════════════════
    # PROFILE 1 — REJECT + WITH
    # VP1 cutoff proof absent + site evidence of recent arrival
    # ══════════════════════════════════════════════════════════════════════════
    {
        "profile_id": 1,
        "category": "pakka_house_status",
        "algo_recommendation": "reject",
        "rule_result": "INELIGIBLE_BY_RULE",
        "signal_direction": "WITH",
        "profile": {
            "name": "Ramesh Jadhav",
            "age": 47,
            "slum": "Bhabrekar Nagar, Andheri (W)",
            "survey_no": "142 (pt), Andheri",
            "occupancy_type": "Residential",
            "claimed_since": 2008,
            "documents": ["Electricity bill (2012)", "Aadhaar", "Self-declaration (A+B)"],
            "voter_roll": "NOT on 2011 or earlier roll",
            "municipal_tax": "None",
            "society": "None",
            "housing": "Tin sheets + tarpaulin",
        },
        "control_note_en": "Applicant claims residence since 2008. Electricity bill from 2012 submitted. No voter roll entry for 2011 or earlier. Self-declarations filed. Aadhaar submitted.",
        "control_note_mr": "अर्जदार २००८ पासून राहत असल्याचा दावा करतो. २०१२ चे वीज बिल सादर. २०११ किंवा त्यापूर्वीची मतदार यादी नोंद नाही. स्वघोषणापत्रे दाखल. आधार सादर.",
        "treatment_note_en": "Applicant claims residence since 2008. Electricity bill from 2012 submitted. No voter roll entry for 2011 or earlier. Self-declarations filed. Aadhaar submitted. During site visit, structure appeared recently reinforced with new tin sheets. Neighbours could not confirm applicant's presence before 2013.",
        "treatment_note_mr": "अर्जदार २००८ पासून राहत असल्याचा दावा करतो. २०१२ चे वीज बिल सादर. २०११ किंवा त्यापूर्वीची मतदार यादी नोंद नाही. स्वघोषणापत्रे दाखल. आधार सादर. क्षेत्रभेटीत संरचना नवीन टिन पत्र्यांनी अलीकडेच मजबूत केलेली दिसली. शेजाऱ्यांना अर्जदाराची २०१३ पूर्वीची उपस्थिती पुष्टी करता आली नाही.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PROFILE 2 — REJECT + WITH
    # D1: family member already received free rehab
    # ══════════════════════════════════════════════════════════════════════════
    {
        "profile_id": 2,
        "category": "family_property",
        "algo_recommendation": "reject",
        "rule_result": "INELIGIBLE_BY_RULE",
        "signal_direction": "WITH",
        "profile": {
            "name": "Sunita Kamble",
            "age": 38,
            "slum": "Rajiv Gandhi Nagar, Bandra (E)",
            "survey_no": "67 (pt), Bandra",
            "occupancy_type": "Residential",
            "claimed_since": 2005,
            "documents": ["Voter roll (2009)", "Aadhaar", "Self-declaration (A+B)", "Electricity bill (2006)"],
            "voter_roll": "2009",
            "municipal_tax": "None",
            "society": "Rajiv Gandhi CHS (registered 2004)",
            "housing": "Semi-pucca (brick + tin roof)",
        },
        "control_note_en": "Applicant on voter roll since 2009. Electricity connection from 2006. Society member since 2004. Self-declarations filed. Aadhaar submitted.",
        "control_note_mr": "अर्जदार २००९ पासून मतदार यादीत. २००६ पासून वीज जोडणी. २००४ पासून सोसायटी सदस्य. स्वघोषणापत्रे दाखल. आधार सादर.",
        "treatment_note_en": "Applicant on voter roll since 2009. Electricity connection from 2006. Society member since 2004. Self-declarations filed. Aadhaar submitted. Husband Prakash Kamble received free rehabilitation flat under SRS scheme in 2017 at same location.",
        "treatment_note_mr": "अर्जदार २००९ पासून मतदार यादीत. २००६ पासून वीज जोडणी. २००४ पासून सोसायटी सदस्य. स्वघोषणापत्रे दाखल. आधार सादर. पती प्रकाश कांबळे यांना २०१७ मध्ये त्याच ठिकाणी SRS योजनेंतर्गत मोफत पुनर्वसन सदनिका मिळाली.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PROFILE 3 — APPROVE + WITH
    # Track A: full documentation + visible hardship
    # ══════════════════════════════════════════════════════════════════════════
    {
        "profile_id": 3,
        "category": "pakka_house_status",
        "algo_recommendation": "approve",
        "rule_result": "ELIGIBLE_BY_RULE",
        "signal_direction": "WITH",
        "profile": {
            "name": "Laxmi Waghmare",
            "age": 52,
            "slum": "Shivaji Nagar, Govandi",
            "survey_no": "203 (pt), Govandi",
            "occupancy_type": "Residential",
            "claimed_since": 1998,
            "documents": ["Voter roll (2000)", "Electricity bill (2003)", "Municipal tax receipt (2005)", "Aadhaar", "Self-declaration (A+B)"],
            "voter_roll": "2000",
            "municipal_tax": "Paid since 2005",
            "society": "Shivaji CHS (founding member, registered 1999)",
            "housing": "Kuccha (bamboo + plastic sheet)",
        },
        "control_note_en": "Applicant on voter roll since 2000. Electricity from 2003. Municipal tax paid since 2005. Society founding member. All documents verified. Pre-cutoff existence confirmed. Current occupancy confirmed via recent voter roll entry.",
        "control_note_mr": "अर्जदार २००० पासून मतदार यादीत. २००३ पासून वीज. २००५ पासून नगरपालिका कर भरला. सोसायटी संस्थापक सदस्य. सर्व कागदपत्रे सत्यापित. कटऑफपूर्व अस्तित्व पुष्टी. अलीकडील मतदार यादी नोंदीद्वारे सध्याचे वास्तव्य पुष्टी.",
        "treatment_note_en": "Applicant on voter roll since 2000. Electricity from 2003. Municipal tax paid since 2005. Society founding member. All documents verified. Pre-cutoff existence confirmed. Current occupancy confirmed via recent voter roll entry. Structure clearly impoverished; verifier notes household visibly in long-term hardship.",
        "treatment_note_mr": "अर्जदार २००० पासून मतदार यादीत. २००३ पासून वीज. २००५ पासून नगरपालिका कर भरला. सोसायटी संस्थापक सदस्य. सर्व कागदपत्रे सत्यापित. कटऑफपूर्व अस्तित्व पुष्टी. अलीकडील मतदार यादी नोंदीद्वारे सध्याचे वास्तव्य पुष्टी. संरचना स्पष्टपणे दरिद्री; सत्यापनकर्त्याने कुटुंब दीर्घकालीन हालाखीत असल्याचे नोंदवले.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PROFILE 4 — APPROVE + WITH
    # Track B: complete transfer + livelihood
    # ══════════════════════════════════════════════════════════════════════════
    {
        "profile_id": 4,
        "category": "tenancy_occupancy",
        "algo_recommendation": "approve",
        "rule_result": "ELIGIBLE_BY_RULE",
        "signal_direction": "WITH",
        "profile": {
            "name": "Abdul Shaikh",
            "age": 34,
            "slum": "Dharavi Cross Road, Mahim",
            "survey_no": "88 (pt), Mahim",
            "occupancy_type": "Residential + Commercial (tailoring)",
            "claimed_since": 2014,
            "documents": ["Voter roll (2019)", "Electricity bill (2015)", "Aadhaar", "Self-declaration (A+B)", "Notarized consent (2014)", "OTC receipt (₹60,000 paid 2019)"],
            "voter_roll": "2019",
            "municipal_tax": "None",
            "society": "None",
            "housing": "Semi-pucca (brick walls, tin roof)",
            "prior_occupant_proof": "Voter roll (2008), Electricity bill (2009)",
        },
        "control_note_en": "Applicant is Track B — arrived 2014. Structure pre-cutoff existence confirmed via prior occupant's voter roll (2008) and electricity bill (2009). Notarized consent and OTC receipt submitted. Current voter roll entry 2019. Site inspection completed.",
        "control_note_mr": "अर्जदार Track B — २०१४ मध्ये आला. पूर्वीच्या रहिवाशाच्या मतदार यादी (२००८) आणि वीज बिल (२००९) द्वारे संरचनेचे कटऑफपूर्व अस्तित्व पुष्टी. नोटरीकृत संमती आणि OTC पावती सादर. सध्याची मतदार यादी नोंद २०१९. क्षेत्र तपासणी पूर्ण.",
        "treatment_note_en": "Applicant is Track B — arrived 2014. Structure pre-cutoff existence confirmed via prior occupant's voter roll (2008) and electricity bill (2009). Notarized consent and OTC receipt submitted. Current voter roll entry 2019. Site inspection completed. Applicant runs small tailoring unit from same structure; family of four shares the space.",
        "treatment_note_mr": "अर्जदार Track B — २०१४ मध्ये आला. पूर्वीच्या रहिवाशाच्या मतदार यादी (२००८) आणि वीज बिल (२००९) द्वारे संरचनेचे कटऑफपूर्व अस्तित्व पुष्टी. नोटरीकृत संमती आणि OTC पावती सादर. सध्याची मतदार यादी नोंद २०१९. क्षेत्र तपासणी पूर्ण. अर्जदार त्याच संरचनेतून लहान शिलाई युनिट चालवतो; चार जणांचे कुटुंब जागा सामायिक करते.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PROFILE 5 — REJECT + WITH
    # D2/D3: non-independence from family member's structure
    # ══════════════════════════════════════════════════════════════════════════
    {
        "profile_id": 5,
        "category": "family_property",
        "algo_recommendation": "reject",
        "rule_result": "INELIGIBLE_BY_RULE",
        "signal_direction": "WITH",
        "profile": {
            "name": "Ganesh Patil",
            "age": 29,
            "slum": "Ambedkar Nagar, Kurla (W)",
            "survey_no": "156 (pt), Kurla",
            "occupancy_type": "Residential",
            "claimed_since": 2010,
            "documents": ["Aadhaar (address: father's structure)", "Self-declaration (A+B)"],
            "voter_roll": "Same address as father Mohan Patil",
            "municipal_tax": "None",
            "society": "None",
            "housing": "Claimed separate structure (no photographic evidence)",
            "father_status": "Mohan Patil — eligible, separate Annexure-II filed",
        },
        "control_note_en": "Applicant claims separate structure adjacent to father Mohan Patil's structure. Voter roll shows same address as father. No independent electricity connection. No separate municipal tax assessment. Father has filed separate Annexure-II and is eligible.",
        "control_note_mr": "अर्जदार वडील मोहन पाटील यांच्या संरचनेला लागून वेगळी संरचना असल्याचा दावा करतो. मतदार यादीत वडिलांचाच पत्ता. स्वतंत्र वीज जोडणी नाही. स्वतंत्र नगरपालिका कर मूल्यांकन नाही. वडिलांनी स्वतंत्र Annexure-II दाखल केला आणि ते पात्र आहेत.",
        "treatment_note_en": "Applicant claims separate structure adjacent to father Mohan Patil's structure. Voter roll shows same address as father. No independent electricity connection. No separate municipal tax assessment. Father has filed separate Annexure-II and is eligible. During site visit, no visible partition or separate entrance was observed between the two claimed structures.",
        "treatment_note_mr": "अर्जदार वडील मोहन पाटील यांच्या संरचनेला लागून वेगळी संरचना असल्याचा दावा करतो. मतदार यादीत वडिलांचाच पत्ता. स्वतंत्र वीज जोडणी नाही. स्वतंत्र नगरपालिका कर मूल्यांकन नाही. वडिलांनी स्वतंत्र Annexure-II दाखल केला आणि ते पात्र आहेत. क्षेत्रभेटीत दोन दावा केलेल्या संरचनांमध्ये कोणतीही दृश्य विभाजन किंवा स्वतंत्र प्रवेशद्वार दिसले नाही.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PROFILE 6 — REJECT + AGAINST
    # VP2 timing ambiguous + neighbour confirmation creates doubt
    # ══════════════════════════════════════════════════════════════════════════
    {
        "profile_id": 6,
        "category": "tenancy_occupancy",
        "algo_recommendation": "reject",
        "rule_result": "INELIGIBLE_BY_RULE",
        "signal_direction": "AGAINST",
        "profile": {
            "name": "Meena Gupta",
            "age": 44,
            "slum": "Transit Camp, Goregaon (E)",
            "survey_no": "211 (pt), Goregaon",
            "occupancy_type": "Residential",
            "claimed_since": 2009,
            "documents": ["Electricity bill (Jan 2012, connection date Nov 2011)", "Aadhaar", "Self-declaration (A+B)"],
            "voter_roll": "NOT on roll before 2014",
            "municipal_tax": "None",
            "society": "None",
            "housing": "Kuccha (tin + bamboo)",
        },
        "control_note_en": "Applicant's earliest document is electricity bill from January 2012 with connection date November 2011. No voter roll entry before 2014. Self-declarations filed. Aadhaar submitted. No other pre-cutoff proof available.",
        "control_note_mr": "अर्जदाराचे सर्वात जुने कागदपत्र जानेवारी २०१२ चे वीज बिल आहे ज्यावर जोडणी तारीख नोव्हेंबर २०११ आहे. २०१४ पूर्वी मतदार यादी नोंद नाही. स्वघोषणापत्रे दाखल. आधार सादर. इतर कटऑफपूर्व पुरावा उपलब्ध नाही.",
        "treatment_note_en": "Applicant's earliest document is electricity bill from January 2012 with connection date November 2011. No voter roll entry before 2014. Self-declarations filed. Aadhaar submitted. Applicant claims continuous residence since 2009; surrounding households confirm long-term presence.",
        "treatment_note_mr": "अर्जदाराचे सर्वात जुने कागदपत्र जानेवारी २०१२ चे वीज बिल आहे ज्यावर जोडणी तारीख नोव्हेंबर २०११ आहे. २०१४ पूर्वी मतदार यादी नोंद नाही. स्वघोषणापत्रे दाखल. आधार सादर. अर्जदार २००९ पासून सतत राहत असल्याचा दावा करतो; आसपासच्या कुटुंबांनी दीर्घकालीन उपस्थिती पुष्टी केली.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PROFILE 7 — APPROVE + AGAINST
    # Eligible but affluence indicators inconsistent
    # ══════════════════════════════════════════════════════════════════════════
    {
        "profile_id": 7,
        "category": "visible_affluence",
        "algo_recommendation": "approve",
        "rule_result": "ELIGIBLE_BY_RULE",
        "signal_direction": "AGAINST",
        "profile": {
            "name": "Priya Deshmukh",
            "age": 41,
            "slum": "Ambujwadi, Malad (W)",
            "survey_no": "178 (pt), Malad",
            "occupancy_type": "Residential",
            "claimed_since": 2003,
            "documents": ["Voter roll (2005)", "Electricity bill (2004)", "Aadhaar", "Self-declaration (A+B)"],
            "voter_roll": "2005",
            "municipal_tax": "None",
            "society": "Ambujwadi CHS (registered 2006)",
            "housing": "Semi-pucca (brick + asbestos roof)",
        },
        "control_note_en": "Applicant on voter roll since 2005. Electricity from 2004. Society member since 2006. Self-declarations filed. Aadhaar submitted. Pre-cutoff existence confirmed. Current occupancy verified.",
        "control_note_mr": "अर्जदार २००५ पासून मतदार यादीत. २००४ पासून वीज. २००६ पासून सोसायटी सदस्य. स्वघोषणापत्रे दाखल. आधार सादर. कटऑफपूर्व अस्तित्व पुष्टी. सध्याचे वास्तव्य सत्यापित.",
        "treatment_note_en": "Applicant on voter roll since 2005. Electricity from 2004. Society member since 2006. Self-declarations filed. Aadhaar submitted. Pre-cutoff existence confirmed. Current occupancy verified. Locality is high-income zone; lifestyle indicators (vehicle, household interior) inconsistent with declared status.",
        "treatment_note_mr": "अर्जदार २००५ पासून मतदार यादीत. २००४ पासून वीज. २००६ पासून सोसायटी सदस्य. स्वघोषणापत्रे दाखल. आधार सादर. कटऑफपूर्व अस्तित्व पुष्टी. सध्याचे वास्तव्य सत्यापित. परिसर उच्च-उत्पन्न क्षेत्र; जीवनशैली निर्देशक (वाहन, घराचे आतील) जाहीर स्थितीशी विसंगत.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PROFILE 8 — APPROVE + AGAINST
    # Eligible but family ancestral land disclosure
    # ══════════════════════════════════════════════════════════════════════════
    {
        "profile_id": 8,
        "category": "family_property",
        "algo_recommendation": "approve",
        "rule_result": "ELIGIBLE_BY_RULE",
        "signal_direction": "AGAINST",
        "profile": {
            "name": "Vitthal More",
            "age": 56,
            "slum": "Panchsheel Nagar, Chembur",
            "survey_no": "134 (pt), Chembur",
            "occupancy_type": "Residential",
            "claimed_since": 2001,
            "documents": ["Voter roll (2004)", "Electricity bill (2002)", "Property tax receipt (2003)", "Aadhaar", "Self-declaration (A+B)"],
            "voter_roll": "2004",
            "municipal_tax": "Paid since 2003",
            "society": "Panchsheel CHS (registered 2002)",
            "housing": "Semi-pucca (brick + corrugated sheet)",
        },
        "control_note_en": "Applicant on voter roll since 2004. Electricity from 2002. Property tax paid. Society member. All documents verified. Pre-cutoff existence confirmed. Self-declaration states no other property owned.",
        "control_note_mr": "अर्जदार २००४ पासून मतदार यादीत. २००२ पासून वीज. मालमत्ता कर भरला. सोसायटी सदस्य. सर्व कागदपत्रे सत्यापित. कटऑफपूर्व अस्तित्व पुष्टी. स्वघोषणापत्रात इतर मालमत्ता नसल्याचे नमूद.",
        "treatment_note_en": "Applicant on voter roll since 2004. Electricity from 2002. Property tax paid. Society member. All documents verified. Pre-cutoff existence confirmed. Self-declaration states no other property owned. Family holds ancestral agricultural land in Satara district per applicant disclosure.",
        "treatment_note_mr": "अर्जदार २००४ पासून मतदार यादीत. २००२ पासून वीज. मालमत्ता कर भरला. सोसायटी सदस्य. सर्व कागदपत्रे सत्यापित. कटऑफपूर्व अस्तित्व पुष्टी. स्वघोषणापत्रात इतर मालमत्ता नसल्याचे नमूद. अर्जदाराच्या खुलाशानुसार कुटुंबाची सातारा जिल्ह्यात पूर्वजांची शेतजमीन आहे.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PROFILE 9 — REJECT + AGAINST
    # Track B incomplete but hardship framing
    # ══════════════════════════════════════════════════════════════════════════
    {
        "profile_id": 9,
        "category": "sympathy_framing",
        "algo_recommendation": "reject",
        "rule_result": "INELIGIBLE_BY_RULE",
        "signal_direction": "AGAINST",
        "profile": {
            "name": "Rekha Yadav",
            "age": 36,
            "slum": "Kranti Nagar, Bhandup (W)",
            "survey_no": "195 (pt), Bhandup",
            "occupancy_type": "Residential",
            "claimed_since": 2015,
            "documents": ["Voter roll (2019)", "Aadhaar", "Self-declaration (A+B)", "Electricity bill (2016)"],
            "voter_roll": "2019",
            "municipal_tax": "None",
            "society": "None",
            "housing": "Kuccha (tin + tarpaulin)",
            "transfer_proof": "Handwritten consent (NOT notarized)",
            "otc": "NOT paid",
            "prior_occupant_proof": "Voter roll (2007)",
        },
        "control_note_en": "Applicant is Track B — arrived 2015. Structure pre-cutoff existence confirmed via prior occupant's voter roll. Transfer consent letter is handwritten and not notarized — does not meet GR requirement. OTC not paid. Site inspection pending.",
        "control_note_mr": "अर्जदार Track B — २०१५ मध्ये आला. पूर्वीच्या रहिवाशाच्या मतदार यादीद्वारे संरचनेचे कटऑफपूर्व अस्तित्व पुष्टी. हस्तांतरण संमतीपत्र हस्तलिखित आणि नोटरीकृत नाही — GR आवश्यकता पूर्ण करत नाही. OTC भरलेला नाही. क्षेत्र तपासणी प्रलंबित.",
        "treatment_note_en": "Applicant is Track B — arrived 2015. Structure pre-cutoff existence confirmed via prior occupant's voter roll. Transfer consent letter is handwritten and not notarized — does not meet GR requirement. OTC not paid. Site inspection pending. Verifier notes household clearly in hardship; applicant claims prior occupant deceased.",
        "treatment_note_mr": "अर्जदार Track B — २०१५ मध्ये आला. पूर्वीच्या रहिवाशाच्या मतदार यादीद्वारे संरचनेचे कटऑफपूर्व अस्तित्व पुष्टी. हस्तांतरण संमतीपत्र हस्तलिखित आणि नोटरीकृत नाही — GR आवश्यकता पूर्ण करत नाही. OTC भरलेला नाही. क्षेत्र तपासणी प्रलंबित. सत्यापनकर्त्याने कुटुंब स्पष्टपणे हालाखीत असल्याचे नोंदवले; अर्जदार पूर्वीचा रहिवासी मृत असल्याचे सांगतो.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PROFILE 10 — APPROVE + WITH
    # Track A: long-standing, multiple proofs, deteriorating structure
    # ══════════════════════════════════════════════════════════════════════════
    {
        "profile_id": 10,
        "category": "pakka_house_status",
        "algo_recommendation": "approve",
        "rule_result": "ELIGIBLE_BY_RULE",
        "signal_direction": "WITH",
        "profile": {
            "name": "Baburao Gaikwad",
            "age": 61,
            "slum": "Dr. Ambedkar Colony, Sion",
            "survey_no": "89 (pt), Sion",
            "occupancy_type": "Residential",
            "claimed_since": 1995,
            "documents": ["Voter roll (1998)", "Electricity bill (1997)", "Property tax receipt (2000)", "Aadhaar", "Self-declaration (A+B)"],
            "voter_roll": "1998",
            "municipal_tax": "Paid since 2000",
            "society": "Ambedkar CHS (founding member, registered 1997)",
            "housing": "Kuccha (original bamboo structure, deteriorating)",
        },
        "control_note_en": "Applicant on voter roll since 1998. Electricity from 1997. Property tax paid since 2000. Society founding member. All documents verified. Pre-cutoff existence well established. Current occupancy confirmed.",
        "control_note_mr": "अर्जदार १९९८ पासून मतदार यादीत. १९९७ पासून वीज. २००० पासून मालमत्ता कर भरला. सोसायटी संस्थापक सदस्य. सर्व कागदपत्रे सत्यापित. कटऑफपूर्व अस्तित्व सुस्थापित. सध्याचे वास्तव्य पुष्टी.",
        "treatment_note_en": "Applicant on voter roll since 1998. Electricity from 1997. Property tax paid since 2000. Society founding member. All documents verified. Pre-cutoff existence well established. Current occupancy confirmed. Structure is original from 1995, deteriorating; family long-resident and dependent on this dwelling.",
        "treatment_note_mr": "अर्जदार १९९८ पासून मतदार यादीत. १९९७ पासून वीज. २००० पासून मालमत्ता कर भरला. सोसायटी संस्थापक सदस्य. सर्व कागदपत्रे सत्यापित. कटऑफपूर्व अस्तित्व सुस्थापित. सध्याचे वास्तव्य पुष्टी. संरचना १९९५ ची मूळ, खराब होत आहे; कुटुंब दीर्घकाळ राहिलेले आणि या निवासस्थानावर अवलंबून.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PROFILE 11 — REJECT + WITH
    # D4: false declaration — owns alternate property
    # ══════════════════════════════════════════════════════════════════════════
    {
        "profile_id": 11,
        "category": "documentation",
        "algo_recommendation": "reject",
        "rule_result": "INELIGIBLE_BY_RULE",
        "signal_direction": "WITH",
        "profile": {
            "name": "Nilesh Pawar",
            "age": 39,
            "slum": "Adarsh Nagar, Worli",
            "survey_no": "223 (pt), Worli",
            "occupancy_type": "Residential",
            "claimed_since": 2006,
            "documents": ["Voter roll (2009)", "Electricity bill (2007)", "Aadhaar", "Self-declaration (A+B)"],
            "voter_roll": "2009",
            "municipal_tax": "None",
            "society": "None",
            "housing": "Semi-pucca (brick + tile roof)",
            "property_flag": "Owns 1BHK in Virar (purchased 2018) per property records",
        },
        "control_note_en": "Applicant on voter roll since 2009. Electricity from 2007. Self-declarations filed. Pre-cutoff existence confirmed. During verification, property records show applicant owns a 1BHK flat in Virar purchased in 2018. Self-declaration (A) states no other property.",
        "control_note_mr": "अर्जदार २००९ पासून मतदार यादीत. २००७ पासून वीज. स्वघोषणापत्रे दाखल. कटऑफपूर्व अस्तित्व पुष्टी. सत्यापनादरम्यान, मालमत्ता नोंदी दर्शवतात की अर्जदाराने २०१८ मध्ये विरारमध्ये 1BHK फ्लॅट खरेदी केला. स्वघोषणापत्र (A) मध्ये इतर मालमत्ता नसल्याचे नमूद.",
        "treatment_note_en": "Applicant on voter roll since 2009. Electricity from 2007. Self-declarations filed. Pre-cutoff existence confirmed. During verification, property records show applicant owns a 1BHK flat in Virar purchased in 2018. Self-declaration (A) states no other property. Applicant's Virar flat was confirmed via MHADA records cross-check; slum address used only for Aadhaar.",
        "treatment_note_mr": "अर्जदार २००९ पासून मतदार यादीत. २००७ पासून वीज. स्वघोषणापत्रे दाखल. कटऑफपूर्व अस्तित्व पुष्टी. सत्यापनादरम्यान, मालमत्ता नोंदी दर्शवतात की अर्जदाराने २०१८ मध्ये विरारमध्ये 1BHK फ्लॅट खरेदी केला. स्वघोषणापत्र (A) मध्ये इतर मालमत्ता नसल्याचे नमूद. अर्जदाराच्या विरार फ्लॅटची MHADA नोंदी क्रॉस-चेकद्वारे पुष्टी; स्लम पत्ता केवळ आधारसाठी वापरला.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PROFILE 12 — REJECT + AGAINST
    # No documentary proof but neighbour testimony
    # ══════════════════════════════════════════════════════════════════════════
    {
        "profile_id": 12,
        "category": "pakka_house_status",
        "algo_recommendation": "reject",
        "rule_result": "INELIGIBLE_BY_RULE",
        "signal_direction": "AGAINST",
        "profile": {
            "name": "Fatima Ansari",
            "age": 50,
            "slum": "Rafiq Nagar, Mankhurd",
            "survey_no": "247 (pt), Mankhurd",
            "occupancy_type": "Residential",
            "claimed_since": 2007,
            "documents": ["Aadhaar", "Self-declaration (A+B)", "Electricity bill (2013)"],
            "voter_roll": "NOT on any roll before 2014",
            "municipal_tax": "None",
            "society": "None",
            "housing": "Kuccha (tin + plastic sheet)",
        },
        "control_note_en": "Applicant's earliest document is electricity bill from 2013. No voter roll entry before 2014. No other pre-cutoff proof submitted. Self-declarations filed. Aadhaar submitted.",
        "control_note_mr": "अर्जदाराचे सर्वात जुने कागदपत्र २०१३ चे वीज बिल आहे. २०१४ पूर्वी मतदार यादी नोंद नाही. इतर कटऑफपूर्व पुरावा सादर नाही. स्वघोषणापत्रे दाखल. आधार सादर.",
        "treatment_note_en": "Applicant's earliest document is electricity bill from 2013. No voter roll entry before 2014. No other pre-cutoff proof submitted. Self-declarations filed. Aadhaar submitted. Surrounding households confirm continuous presence since at least 2007.",
        "treatment_note_mr": "अर्जदाराचे सर्वात जुने कागदपत्र २०१३ चे वीज बिल आहे. २०१४ पूर्वी मतदार यादी नोंद नाही. इतर कटऑफपूर्व पुरावा सादर नाही. स्वघोषणापत्रे दाखल. आधार सादर. आसपासच्या कुटुंबांनी किमान २००७ पासून सतत उपस्थिती पुष्टी केली.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PROFILE 13 — APPROVE + AGAINST
    # Eligible but non-resident signals
    # ══════════════════════════════════════════════════════════════════════════
    {
        "profile_id": 13,
        "category": "documentation",
        "algo_recommendation": "approve",
        "rule_result": "ELIGIBLE_BY_RULE",
        "signal_direction": "AGAINST",
        "profile": {
            "name": "Rajendra Shirke",
            "age": 45,
            "slum": "Nehru Nagar, Vile Parle (E)",
            "survey_no": "162 (pt), Vile Parle",
            "occupancy_type": "Residential",
            "claimed_since": 2004,
            "documents": ["Voter roll (2005)", "Electricity bill (2006)", "Aadhaar", "Self-declaration (A+B)"],
            "voter_roll": "2005",
            "municipal_tax": "None",
            "society": "Nehru Nagar CHS (registered 2005)",
            "housing": "Semi-pucca (brick + tin roof)",
        },
        "control_note_en": "Applicant on voter roll since 2005. Electricity from 2006. Society member. Self-declarations filed. Aadhaar submitted. Pre-cutoff existence confirmed. Current voter roll entry present.",
        "control_note_mr": "अर्जदार २००५ पासून मतदार यादीत. २००६ पासून वीज. सोसायटी सदस्य. स्वघोषणापत्रे दाखल. आधार सादर. कटऑफपूर्व अस्तित्व पुष्टी. सध्याची मतदार यादी नोंद आहे.",
        "treatment_note_en": "Applicant on voter roll since 2005. Electricity from 2006. Society member. Self-declarations filed. Aadhaar submitted. Pre-cutoff existence confirmed. Current voter roll entry present. During unannounced site visit, structure was locked; neighbours report applicant primarily resides elsewhere; electricity meter shows minimal recent consumption.",
        "treatment_note_mr": "अर्जदार २००५ पासून मतदार यादीत. २००६ पासून वीज. सोसायटी सदस्य. स्वघोषणापत्रे दाखल. आधार सादर. कटऑफपूर्व अस्तित्व पुष्टी. सध्याची मतदार यादी नोंद आहे. अघोषित क्षेत्रभेटीत संरचना बंद होती; शेजारी अर्जदार प्रामुख्याने इतरत्र राहत असल्याचे सांगतात; वीज मीटर अलीकडील कमी वापर दर्शवतो.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PROFILE 14 — APPROVE + AGAINST
    # Eligible but commercial misuse
    # ══════════════════════════════════════════════════════════════════════════
    {
        "profile_id": 14,
        "category": "tenancy_occupancy",
        "algo_recommendation": "approve",
        "rule_result": "ELIGIBLE_BY_RULE",
        "signal_direction": "AGAINST",
        "profile": {
            "name": "Deepak Chavan",
            "age": 48,
            "slum": "Santosh Nagar, Jogeshwari (E)",
            "survey_no": "188 (pt), Jogeshwari",
            "occupancy_type": "Residential",
            "claimed_since": 2002,
            "documents": ["Voter roll (2004)", "Electricity bill (2003)", "Aadhaar", "Self-declaration (A+B)"],
            "voter_roll": "2004",
            "municipal_tax": "None",
            "society": "Santosh Nagar CHS (registered 2003)",
            "housing": "Semi-pucca (brick + asbestos)",
        },
        "control_note_en": "Applicant on voter roll since 2004. Electricity from 2003. Society member. Self-declarations filed. Aadhaar submitted. Pre-cutoff existence confirmed. Current occupancy verified.",
        "control_note_mr": "अर्जदार २००४ पासून मतदार यादीत. २००३ पासून वीज. सोसायटी सदस्य. स्वघोषणापत्रे दाखल. आधार सादर. कटऑफपूर्व अस्तित्व पुष्टी. सध्याचे वास्तव्य सत्यापित.",
        "treatment_note_en": "Applicant on voter roll since 2004. Electricity from 2003. Society member. Self-declarations filed. Aadhaar submitted. Pre-cutoff existence confirmed. Current occupancy verified. During visit, structure observed in use as unauthorized godown; non-resident workers present on premises.",
        "treatment_note_mr": "अर्जदार २००४ पासून मतदार यादीत. २००३ पासून वीज. सोसायटी सदस्य. स्वघोषणापत्रे दाखल. आधार सादर. कटऑफपूर्व अस्तित्व पुष्टी. सध्याचे वास्तव्य सत्यापित. भेटीदरम्यान, संरचना अनधिकृत गोदाम म्हणून वापरात दिसली; परिसरात अनिवासी कामगार उपस्थित.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PROFILE 15 — APPROVE + WITH
    # Track B: clean transfer chain, all additional proofs
    # ══════════════════════════════════════════════════════════════════════════
    {
        "profile_id": 15,
        "category": "tenancy_occupancy",
        "algo_recommendation": "approve",
        "rule_result": "ELIGIBLE_BY_RULE",
        "signal_direction": "WITH",
        "profile": {
            "name": "Kavita Bhosale",
            "age": 33,
            "slum": "Indira Nagar, Borivali (W)",
            "survey_no": "201 (pt), Borivali",
            "occupancy_type": "Residential",
            "claimed_since": 2016,
            "documents": ["Voter roll (2019)", "Electricity bill (2017)", "Aadhaar", "Self-declaration (A+B)", "Notarized consent on stamp paper (2016)", "OTC receipt (₹40,000 paid 2020)", "Employer certificate (2025)", "Child school enrollment (2023)"],
            "voter_roll": "2019",
            "municipal_tax": "None",
            "society": "None",
            "housing": "Semi-pucca (brick + corrugated sheet)",
            "prior_occupant_proof": "Voter roll (2006), Electricity bill (2005)",
        },
        "control_note_en": "Applicant is Track B — arrived 2016. Structure pre-cutoff existence confirmed via prior occupant's voter roll (2006) and electricity bill (2005). Notarized consent on stamp paper submitted. OTC paid. Current voter roll, employer certificate, and school enrollment all confirm current address. Site inspection completed.",
        "control_note_mr": "अर्जदार Track B — २०१६ मध्ये आला. पूर्वीच्या रहिवाशाच्या मतदार यादी (२००६) आणि वीज बिल (२००५) द्वारे संरचनेचे कटऑफपूर्व अस्तित्व पुष्टी. स्टॅम्प पेपरवर नोटरीकृत संमती सादर. OTC भरला. सध्याची मतदार यादी, नियोक्ता प्रमाणपत्र आणि शाळा प्रवेश सर्व सध्याचा पत्ता पुष्टी करतात. क्षेत्र तपासणी पूर्ण.",
        "treatment_note_en": "Applicant is Track B — arrived 2016. Structure pre-cutoff existence confirmed via prior occupant's voter roll (2006) and electricity bill (2005). Notarized consent on stamp paper submitted. OTC paid. Current voter roll, employer certificate, and school enrollment all confirm current address. Site inspection completed. Transfer chain clean and documented; all additional Track B proofs present.",
        "treatment_note_mr": "अर्जदार Track B — २०१६ मध्ये आला. पूर्वीच्या रहिवाशाच्या मतदार यादी (२००६) आणि वीज बिल (२००५) द्वारे संरचनेचे कटऑफपूर्व अस्तित्व पुष्टी. स्टॅम्प पेपरवर नोटरीकृत संमती सादर. OTC भरला. सध्याची मतदार यादी, नियोक्ता प्रमाणपत्र आणि शाळा प्रवेश सर्व सध्याचा पत्ता पुष्टी करतात. क्षेत्र तपासणी पूर्ण. हस्तांतरण साखळी स्वच्छ आणि दस्तऐवजीकृत; सर्व अतिरिक्त Track B पुरावे उपस्थित.",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PROFILE 16 — REJECT + AGAINST
    # Documentary deficiency but long-term residence
    # ══════════════════════════════════════════════════════════════════════════
    {
        "profile_id": 16,
        "category": "documentation",
        "algo_recommendation": "reject",
        "rule_result": "INELIGIBLE_BY_RULE",
        "signal_direction": "AGAINST",
        "profile": {
            "name": "Shankar Mane",
            "age": 58,
            "slum": "Datta Nagar, Mulund (W)",
            "survey_no": "215 (pt), Mulund",
            "occupancy_type": "Residential",
            "claimed_since": 2005,
            "documents": ["Electricity bill (2011, connection date unclear)", "Aadhaar", "Self-declaration (A+B)"],
            "voter_roll": "2009 (name spelled 'Shankarlal Mane' vs 'Shankar Mane' on Aadhaar)",
            "municipal_tax": "None",
            "society": "Dissolved in 2015",
            "housing": "Kuccha (bamboo + tin, original structure)",
        },
        "control_note_en": "Applicant submitted electricity bill from 2011 with unclear connection date. Voter roll entry from 2009 shows different name spelling ('Shankarlal Mane' vs 'Shankar Mane' on Aadhaar). Society dissolved. No property tax record. Name mismatch between documents raises verification concern.",
        "control_note_mr": "अर्जदाराने अस्पष्ट जोडणी तारखेसह २०११ चे वीज बिल सादर केले. २००९ च्या मतदार यादी नोंदीत वेगळे नाव ('शंकरलाल माने' विरुद्ध आधारवर 'शंकर माने'). सोसायटी विसर्जित. मालमत्ता कर नोंद नाही. कागदपत्रांमधील नाव विसंगती सत्यापन चिंता निर्माण करते.",
        "treatment_note_en": "Applicant submitted electricity bill from 2011 with unclear connection date. Voter roll entry from 2009 shows different name spelling ('Shankarlal Mane' vs 'Shankar Mane' on Aadhaar). Society dissolved. No property tax record. Name mismatch between documents raises verification concern. Applicant produced original documents with consistent address; long-term continuous resident per local verification.",
        "treatment_note_mr": "अर्जदाराने अस्पष्ट जोडणी तारखेसह २०११ चे वीज बिल सादर केले. २००९ च्या मतदार यादी नोंदीत वेगळे नाव ('शंकरलाल माने' विरुद्ध आधारवर 'शंकर माने'). सोसायटी विसर्जित. मालमत्ता कर नोंद नाही. कागदपत्रांमधील नाव विसंगती सत्यापन चिंता निर्माण करते. अर्जदाराने सुसंगत पत्त्यासह मूळ कागदपत्रे सादर केली; स्थानिक सत्यापनानुसार दीर्घकालीन सतत रहिवासी.",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# SEEDER
# Creates 32 vignettes: 16 profiles × 2 arms (control + treatment).
# No list coupling — session-time logic handles randomisation.
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
                    list_assignment     = None,
                    used_count          = 0,
                )
                db.add(v)
                created += 1

        db.commit()

        print(f"Seeded {created} vignettes (pool_version={POOL_VERSION}).")
        print()
        print("Pool structure:")
        print("  16 profiles × 2 arms = 32 vignette objects")
        print("  Session-time: draw 12 from 16, assign 6 control + 6 treatment")
        print()
        print("Cell distribution (balanced 4×4):")
        print("  APPROVE + WITH:    profiles 3, 4, 10, 15     (4)")
        print("  APPROVE + AGAINST: profiles 7, 8, 13, 14     (4)")
        print("  REJECT  + WITH:    profiles 1, 2, 5, 11      (4)")
        print("  REJECT  + AGAINST: profiles 6, 9, 12, 16     (4)")
        print()

        # Verify
        vigs = db.query(Vignette).all()
        ct = sum(1 for v in vigs if v.arm == ArmEnum.CONTROL)
        tr = sum(1 for v in vigs if v.arm == ArmEnum.TREATMENT)
        app = sum(1 for v in vigs if v.algo_recommendation == AlgoRecommendationEnum.APPROVE)
        rej = sum(1 for v in vigs if v.algo_recommendation == AlgoRecommendationEnum.REJECT)
        print(f"  Total: {len(vigs)} | Control: {ct} Treatment: {tr} | Approve: {app} Reject: {rej}")
        print()
        print("GR grounding: ZoPuDho-0810/Pr.Kr.96/2018/ZoPaSu-1")
        print("Sources: Phase 1 corpus (12 profiles) + GR disqualifications (4 profiles)")
        print()
        print("Marathi translations require verification before pilot deployment.")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed SARAL v2 Phase 2 vignette pool")
    parser.add_argument("--clear", action="store_true", help="Drop existing vignettes before seeding")
    args = parser.parse_args()
    seed(clear=args.clear)