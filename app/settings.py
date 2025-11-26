# app/settings.py
import os
from functools import lru_cache

class Settings:
    # --- VERSIONING ---
    APP_VERSION = "1.1.0-pilot"  # Semantic Versioning
    MODEL_VERSION = "v1-logit-nb" # Ties code to specific model artifacts
    
    # --- ENVIRONMENT ---
    ENV = os.getenv("SARAL_ENV", "production") # local | test | production
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./saral.db")
    MOCK_OTP = os.getenv("MOCK_OTP", "123456")
    
    # --- THREAT MODEL LIMITS ---
    MAX_RETRY_COUNT = 3       # Max attempts per citizen hash
    RETRY_WINDOW_MINUTES = 15 # Time window for velocity check
    
    # --- PRIVACY ---
    PII_RETENTION_HOURS = 24  # Data scrubbing window

@lru_cache
def get_settings():
    return Settings()