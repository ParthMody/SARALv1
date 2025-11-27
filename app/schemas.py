# app/schemas.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, List, Annotated

from pydantic import BaseModel, Field, StringConstraints


class StatusEnum(str, Enum):
    NEW = "NEW"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Profile(BaseModel):
    """
    Citizen profile used for triage and ML.

    Defaults ensure:
    - Requests without `profile` don't 422.
    - Code can safely access `profile.income`, etc.
    - Constraints still enforced when values are present.
    """
    age: int = Field(18, ge=18, le=100)
    gender: str = Field("O", pattern="^(M|F|O)$")
    income: int = Field(0, ge=0)
    education_years: int = Field(0, ge=0)
    rural: int = Field(0, ge=0, le=1)
    caste_marginalized: int = Field(0, ge=0, le=1)

    model_config = {"from_attributes": True}


class CaseCreate(BaseModel):
    """
    Input schema for /cases/ POST.

    Key robustness points:
    - `profile` always exists (default_factory=Profile), so no None access.
    - Telemetry fields are optional but always defined.
    """
    citizen_hash: Annotated[
        str,
        StringConstraints(
            min_length=1,
            max_length=64,
            pattern=r"^[A-Za-z0-9_\-\$]+$",
        ),
    ]
    scheme_code: str
    source: str

    locale: str = "en"
    profile: Profile = Field(default_factory=Profile)
    message_text: Optional[str] = None

    # Telemetry & Persistence
    session_id: Optional[str] = None
    meta_duration_seconds: Optional[int] = 0

    model_config = {"from_attributes": True}


class CaseResponse(BaseModel):
    """
    Outbound schema for case responses.

    Includes:
    - Core case metadata
    - Experiment fields (arm, assignment_reason, ai_shown)
    - AI fields (review_confidence, audit_flag, flag_reason, intent_label)
    - Convenience fields (documents, alternatives)
    """
    id: str
    scheme_code: str
    status: StatusEnum
    locale: str
    created_at: datetime

    # AI / Science Fields
    review_confidence: Optional[float] = None
    audit_flag: bool = False
    flag_reason: Optional[str] = None
    intent_label: Optional[str] = None

    # Experiment / RCT Fields
    arm: str
    assignment_reason: Optional[str] = None
    ai_shown: Optional[bool] = None
    meta_duration_seconds: Optional[int] = None

    # Value Add (Safe Defaults)
    documents: List[str] = Field(default_factory=list)
    alternatives: List[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}
