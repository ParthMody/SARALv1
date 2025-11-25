# app/schemas.py
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from typing import Optional

class StatusEnum(str, Enum):
    NEW = "NEW"; IN_REVIEW = "IN_REVIEW"; APPROVED = "APPROVED"; REJECTED = "REJECTED"

# --- NEW: Define the Profile Input ---
class Profile(BaseModel):
    age: int = Field(..., ge=18, le=100)
    gender: str = Field(..., pattern="^(M|F|O)$")
    income: int = Field(..., ge=0)
    education_years: int = Field(..., ge=0)
    rural: int = Field(..., ge=0, le=1)
    caste_marginalized: int = Field(..., ge=0, le=1)

class CaseCreate(BaseModel):
    citizen_hash: str = Field(..., min_length=5)
    scheme_code: str
    source: str
    locale: str = "en"
    
    # --- NEW: Accept Profile & Message ---
    profile: Profile  
    message_text: Optional[str] = None

class CaseResponse(BaseModel):
    id: str
    scheme_code: str
    status: StatusEnum
    locale: str
    created_at: datetime
    # Return the AI decision to the client (optional, but good for debugging)
    review_confidence: Optional[float] = None
    audit_flag: bool = False

    class Config:
        from_attributes = True