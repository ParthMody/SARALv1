# app/settings.py
import os
from functools import lru_cache


class Settings:
    APP_VERSION:    str = "2.0.0-dev"
    SCHEMA_VERSION: str = "v2-experiment"
    POOL_VERSION:   str = "v2.0"

    # Session design constants (TDD §5.2)
    CASES_PER_SESSION:  int = 16
    CONTROL_PER_SESSION:   int = 8
    TREATMENT_PER_SESSION: int = 8

    # Secondary review experience threshold (TDD §9.2)
    SENIOR_EXPERIENCE_GAP: int = 10

    ENV:          str = os.getenv("SARAL_ENV",    "development")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./saral_v2.db")

    # Admin panel auth — replace with a real secret in production
    ADMIN_SECRET: str = os.getenv("SARAL_ADMIN_SECRET", "dev_admin_change_me")


@lru_cache
def get_settings() -> Settings:
    return Settings()