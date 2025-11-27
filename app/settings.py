import os
from functools import lru_cache

class Settings:
    # --- EXPERIMENT VERSIONING ---
    APP_VERSION = "1.3.1-pilot-integrated"
    RULESET_VERSION = "v1.3-audit-wired"
    MODEL_VERSION = "v1-logit-nb-2025"
    SCHEMA_VERSION = "v1-telemetry-full"

    # --- CONFIG ---
    ENV = os.getenv("SARAL_ENV", "production")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./saral.db")
    MOCK_OTP = os.getenv("MOCK_OTP", "123456")

    # --- SAFETY LIMITS ---
    MAX_RETRY_COUNT = 5
    RETRY_WINDOW_MINUTES = 15
    PILOT_DATA_RETENTION_DAYS = 30

@lru_cache
def get_settings():
    return Settings()
