# app/schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


# ─────────────────────────────────────────────
# Operator / Session
# ─────────────────────────────────────────────

class OperatorCreate(BaseModel):
    """Posted from the login form."""
    initials:         str = Field(..., min_length=1, max_length=8)
    age:              int = Field(..., ge=18, le=80)
    role:             str = Field(..., min_length=1, max_length=64)
    experience_years: int = Field(..., ge=0, le=60)
    locale:           str = Field("en", pattern="^(en|mr)$")


class OperatorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    operator_id:      str
    session_id:       str
    initials:         str
    age:              int
    role:             str
    experience_years: int
    locale:           str
    status:           str
    cases_completed:  int
    created_at:       datetime


# ─────────────────────────────────────────────
# Vignette (what the operator sees)
# ─────────────────────────────────────────────

class VignetteDisplay(BaseModel):
    """
    Served to the operator interface for a single case.
    Never exposes arm — operator must not know which arm they are in.
    """
    model_config = ConfigDict(from_attributes=True)

    case_id:            str
    rule_result:        str
    algo_recommendation: str
    profile_data:       dict
    field_note:         str   # resolved to operator's locale at serve time
    case_sequence:      int   # position within session (1–16)


# ─────────────────────────────────────────────
# Evaluation (operator decision submission)
# ─────────────────────────────────────────────

class EvaluationSubmit(BaseModel):
    """Posted when operator submits a decision on a case."""
    case_id:   str
    decision:  str = Field(..., pattern="^(approve|reject|escalate)$")
    reasoning: str = Field(..., min_length=1, max_length=1000)


class EvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                 int
    operator_id:        str
    session_id:         str
    case_id:            str
    arm:                str
    algo_recommendation: str
    decision:           Optional[str]
    reasoning:          Optional[str]
    override:           Optional[bool]
    response_time_sec:  Optional[float]
    case_sequence:      int
    timestamp_open:     Optional[datetime]
    timestamp_submit:   Optional[datetime]


# ─────────────────────────────────────────────
# Post-task Survey
# ─────────────────────────────────────────────

class SurveySubmit(BaseModel):
    """Posted at session close — all 3 Likert items required."""
    salience_rating:   int = Field(..., ge=1, le=5)
    standout_rating:   int = Field(..., ge=1, le=5)
    confidence_rating: int = Field(..., ge=1, le=5)


class SurveyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                int
    operator_id:       str
    session_id:        str
    salience_rating:   int
    standout_rating:   int
    confidence_rating: int
    submitted_at:      datetime


# ─────────────────────────────────────────────
# Second Review
# ─────────────────────────────────────────────

class SecondReviewSubmit(BaseModel):
    secondary_decision: str = Field(..., pattern="^(approve|reject|escalate)$")


class SecondReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                    int
    case_id:               str
    review_type:           Optional[str]
    experience_gap:        Optional[int]
    secondary_decision:    Optional[str]
    # primary_decision is intentionally excluded from this schema
    # — it is never sent to the secondary reviewer


# ─────────────────────────────────────────────
# Admin / Export
# ─────────────────────────────────────────────

class SessionSummary(BaseModel):
    """Lightweight row for admin session monitor."""
    model_config = ConfigDict(from_attributes=True)

    operator_id:      str
    session_id:       str
    initials:         str
    role:             str
    experience_years: int
    locale:           str
    status:           str
    cases_completed:  int
    created_at:       datetime
    completed_at:     Optional[datetime]