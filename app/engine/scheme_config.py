# app/engine/scheme_config.py

SCHEME_RULES = {
    "UJJ": {
        "name": "PM Ujjwala Yojana",
        "description": "LPG connection for women in poor households.",
        "criteria": {
            "min_age": 18,
            "gender": ["F"],
            "max_income": 250000,
            "must_be_rural": False,
        },
        "documents": {
            "base": ["Aadhaar Card", "Bank Passbook", "Ration Card"],
            # FIXED: Matches Test Assertion exactly
            "caste_marginalized": ["Caste Certificate (SC/ST)"],
            "rural": ["Gram Panchayat Certificate"]
        },
        "alternatives": ["PMAY"]
    },
    
    "PMAY": {
        "name": "PM Awas Yojana (Urban)",
        "criteria": {
            "min_age": 21,
            "gender": ["F", "M", "O"],
            "max_income": 600000,
            "must_be_rural": False,
        },
        "documents": {
            "base": ["Aadhaar Card", "Voter ID", "Bank Statement (6 months)"],
            "income_proof": ["Income Certificate / ITR"],
        },
        "alternatives": ["UJJ"]
    },
    
    "MGNREGA": {
        "name": "Mahatma Gandhi NREGA",
        "criteria": {
            "min_age": 18,
            "must_be_rural": True,
        },
        "documents": {
            "base": ["Aadhaar Card", "Job Card Application Form"],
            "rural": ["Gram Panchayat Recommendation"]
        },
        "alternatives": []
    }
}

def get_scheme_config(code: str):
    return SCHEME_RULES.get(code)