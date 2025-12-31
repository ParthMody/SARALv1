# app/schemas.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, List, Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints, ConfigDict, field_validator


class StatusEnum(str, Enum):
    NEW = "NEW"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


IncomePeriod = Literal["monthly", "annual"]


class Profile(BaseModel):
    age: int = Field(18, ge=18, le=100)
    gender: str = Field("O", pattern="^(M|F|O)$")

    income: int = Field(0, ge=0)
    income_period: IncomePeriod = Field(..., description="monthly or annual")

    education_years: int = Field(0, ge=0)
    rural: int = Field(0, ge=0, le=1)
    caste_marginalized: int = Field(0, ge=0, le=1)

    model_config = ConfigDict(from_attributes=True)


class CaseCreate(BaseModel):
    citizen_hash: Annotated[
        str,
        StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-\$]+$"),
    ]
    scheme_code: str
    source: str
    locale: str = "en"
    profile: Profile = Field(default_factory=Profile)
    message_text: Optional[str] = None
    session_id: Optional[str] = None
    meta_duration_seconds: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)


class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scheme_code: str
    status: StatusEnum
    locale: str
    arm: str
    created_at: datetime

    # BAU (both arms)
    rule_result: Optional[str] = None
    rule_reasons: List[str] = Field(default_factory=list)
    documents: List[str] = Field(default_factory=list)

    # ML (treatment only in UI/response)
    review_confidence: Optional[float] = None
    risk_score: Optional[float] = None
    risk_band: Optional[str] = None
    top_reasons: List[str] = Field(default_factory=list)
    decision_support_shown: Optional[bool] = None
    audit_flag: Optional[bool] = None

    # RCT meta
    assignment_reason: Optional[str] = None
    meta_duration_seconds: Optional[int] = None

    # Operator disposition
    final_action: Optional[str] = None
    reason_code: Optional[str] = None
    override_flag: Optional[bool] = None

    @field_validator("rule_reasons", "documents", "top_reasons", mode="before")
    @classmethod
    def _coerce_list(cls, v: Any):
        if v is None:
            return []
        if isinstance(v, list):
            return v
        return []
