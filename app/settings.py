# app/settings.py
import os


class Settings:
    APP_VERSION:        str = "2.5.0"
    SCHEMA_VERSION:     str = "v2.5-prolific"
    POOL_VERSION:       str = "v2.4-mumbai-final"
    INSTRUMENT_VERSION: str = "v2.5"

    # Session design
    CASES_PER_SESSION:     int = 12
    PROFILES_TOTAL:        int = 16

    # Fast response threshold — flag, don't block
    FAST_RESPONSE_THRESHOLD_SEC: float = 8.0  # TDD says 8s for Prolific

    # Minimum session duration for exclusion flagging (seconds)
    MIN_SESSION_DURATION_SEC: float = 300.0  # 5 minutes

    # Secondary review experience threshold (legacy, kept for compat)
    SENIOR_EXPERIENCE_GAP: int = 10

    ENV:          str = os.getenv("SARAL_ENV", "development")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./saral_v2.db")

    # Admin
    ADMIN_SECRET: str = os.getenv("SARAL_ADMIN_SECRET", "dev_admin_change_me")

    # Prolific
    PROLIFIC_COMPLETION_URL: str = os.getenv(
        "PROLIFIC_COMPLETION_URL",
        "https://app.prolific.com/submissions/complete?cc={code}"
    )

    # PIS URL (linked from consent screen)
    PIS_URL: str = os.getenv(
        "PIS_URL",
        "https://parthmody.me/saral-materials"
    )


def get_settings() -> Settings:
    return Settings()