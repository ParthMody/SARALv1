# app/engine/scheme_config.py

SCHEME_CONFIG = {
    "PMAY": {
        "criteria": {
            "min_age": 18,
            "gender": [],  # no restriction
            "must_be_rural": False,
            "requires_marginalized": False,  # keep explicit for consistency

            # income bands are config, not code
            "income_bands": [
                {"name": "EWS", "max": 300_000},
                {"name": "LIG", "max": 600_000},
                {"name": "MIG_I", "max": 1_200_000},
                {"name": "MIG_II", "max": 1_800_000},
            ],
        },
        "alternatives": ["STATE_HOUSING", "RENTAL_SUPPORT"],
    },

    "UJJ": {
        "criteria": {
            "min_age": 18,
            "gender": [],                 # explicit
            "must_be_rural": True,
            "requires_marginalized": False,
            "income_bands": [],           # explicit
        },
        "alternatives": [],
    },
}


def get_scheme_config(code: str):
    return SCHEME_CONFIG.get(code)
