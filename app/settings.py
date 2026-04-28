# app/settings.py
import os
from functools import lru_cache


class Settings:
    APP_VERSION:        str = "2.1.0"
    SCHEMA_VERSION:     str = "v2.1-phase2"
    POOL_VERSION:       str = "v2.1-mumbai"
    INSTRUMENT_VERSION: str = "v2.1"           # item 10

    # Session design — 16 profiles in pool, each operator draws 12 (6 control + 6 treatment)
    CASES_PER_SESSION:     int = 12
    PROFILES_TOTAL:        int = 16

    # Fast response threshold (item 4) — flag, don't block
    FAST_RESPONSE_THRESHOLD_SEC: float = 5.0

    # Secondary review experience threshold
    SENIOR_EXPERIENCE_GAP: int = 10

    ENV:          str = os.getenv("SARAL_ENV",    "development")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./saral.db")

    # Admin panel auth — replace with a real secret in production
    ADMIN_SECRET: str = os.getenv("SARAL_ADMIN_SECRET", "dev_admin_change_me")


@lru_cache
def get_settings() -> Settings:
    return Settings()