# app/engine/scheme_config.py

SCHEME_CONFIG = {
    "PMAY": {
        "description": "Pradhan Mantri Awas Yojana (Urban)",
        "criteria": {
            "min_age": 18,
            "max_age": 70,
            "gender": ["F", "M", "O"], 
            "must_be_rural": False,  # PMAY-U is Urban
            "requires_marginalized": False,

            # CONFIG DECISION: 
            # We strictly enforce EWS/LIG for the pilot.
            # We exclude MIG (Middle Income) so that high-earners (>6L) are rejected.
            "income_bands": [
                {"name": "EWS (Economically Weaker)", "max": 300_000},
                {"name": "LIG (Low Income Group)", "max": 600_000},
                # {"name": "MIG_I", "max": 1_200_000},  <-- Commented out for Pilot
                # {"name": "MIG_II", "max": 1_800_000}, <-- Commented out for Pilot
            ],
        },
        "alternatives": ["Rent Agreement Support", "Shelter Homes"],
    },

    "UJJ": {
        "description": "Pradhan Mantri Ujjwala Yojana (LPG)",
        "criteria": {
            "min_age": 18,
            "gender": ["F"],          # STRICT: Only women can be the primary applicant
            "must_be_rural": False,   # Can be urban poor too
            "requires_marginalized": False,
            
            # FIX: Added a cap so rich people get rejected
            "income_bands": [
                {"name": "BPL / Ration Card Holder", "max": 250_000} 
            ],
        },
        "alternatives": ["General LPG Connection", "State Subsidy"],
    },
}

def get_scheme_config(code: str):
    if not code:
        return None
    return SCHEME_CONFIG.get(code.upper())