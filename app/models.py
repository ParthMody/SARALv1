# app/models.py
from __future__ import annotations

import enum
import uuid
import json
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Enum as SAEnum,
    ForeignKey,
    DateTime,
    Float,
    Boolean,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func
from sqlalchemy.types import TypeDecorator, TEXT

from .db import Base


# ─────────────────────────────────────────────
# SQLite-safe JSON helpers (carried from v1.3)
# ─────────────────────────────────────────────

class JsonList(TypeDecorator):
    """Stores a Python list as a JSON array string."""
    impl = TEXT
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return "[]"
        if isinstance(value, list):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, str):
            s = value.strip()
            return s if s else "[]"
        return "[]"

    def process_result_value(self, value, dialect):
        if not value:
            return []
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []


class JsonDict(TypeDecorator):
    """Stores a Python dict as a JSON object string."""
    impl = TEXT
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return "{}"
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, str):
            s = value.strip()
            return s if s else "{}"
        return "{}"

    def process_result_value(self, value, dialect):
        if not value:
            return {}
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class LocaleEnum(str, enum.Enum):
    EN = "en"
    MR = "mr"


class ArmEnum(str, enum.Enum):
    CONTROL   = "control"
    TREATMENT = "treatment"


class AlgoRecommendationEnum(str, enum.Enum):
    APPROVE = "approve"
    REJECT  = "reject"


class RuleResultEnum(str, enum.Enum):
    ELIGIBLE_BY_RULE   = "ELIGIBLE_BY_RULE"
    INELIGIBLE_BY_RULE = "INELIGIBLE_BY_RULE"


class DecisionEnum(str, enum.Enum):
    APPROVE  = "approve"
    REJECT   = "reject"
    ESCALATE = "escalate"


class ReviewTypeEnum(str, enum.Enum):
    EXPERIENCED = "experienced"
    RANDOM      = "random"


class SessionStatusEnum(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    ABANDONED   = "abandoned"


class AuditActionEnum(str, enum.Enum):
    LOGIN          = "LOGIN"
    SESSION_START  = "SESSION_START"
    CASE_OPEN      = "CASE_OPEN"
    CASE_SUBMIT    = "CASE_SUBMIT"
    SURVEY_SUBMIT  = "SURVEY_SUBMIT"
    SESSION_END    = "SESSION_END"
    ADMIN_EXPORT   = "ADMIN_EXPORT"
    SYSTEM_ERROR   = "SYSTEM_ERROR"


def _uuid() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────
# Core Tables
# ─────────────────────────────────────────────

class Operator(Base):
    """
    Created at login. One row per operator session.
    operator_id is UUID4 — no PII derivation.
    """
    __tablename__ = "operators"

    operator_id  = Column(String, primary_key=True, default=_uuid)
    session_id   = Column(String, nullable=False, unique=True, default=_uuid, index=True)

    # Demographics (login form inputs)
    initials            = Column(String(8),  nullable=False)
    age                 = Column(Integer,    nullable=False)
    role                = Column(String(64), nullable=False)
    experience_years    = Column(Integer,    nullable=False)
    locale              = Column(SAEnum(LocaleEnum), nullable=False, default=LocaleEnum.EN)

    # Session lifecycle
    status       = Column(SAEnum(SessionStatusEnum), nullable=False, default=SessionStatusEnum.IN_PROGRESS)
    cases_assigned   = Column(JsonList, default=list, nullable=False)  # ordered list of case_ids
    cases_completed  = Column(Integer,  nullable=False, default=0)

    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class Vignette(Base):
    """
    Pre-loaded synthetic case pool. 320 rows total:
      160 control  (80 approve, 80 reject)
      160 treatment (80 approve, 80 reject)
    Loaded once by seed script — never mutated at runtime.
    """
    __tablename__ = "vignettes"

    case_id = Column(String, primary_key=True, default=_uuid)

    arm                 = Column(SAEnum(ArmEnum),                nullable=False, index=True)
    algo_recommendation = Column(SAEnum(AlgoRecommendationEnum), nullable=False, index=True)
    rule_result         = Column(SAEnum(RuleResultEnum),         nullable=False)

    # Structured applicant profile (displayed to operator)
    profile_data = Column(JsonDict, nullable=False, default=dict)

    # Field note — sterile (control) or signal-injected (treatment)
    # Stored in both locales; served based on operator.locale at runtime
    field_note_en = Column(Text, nullable=False, default="")
    field_note_mr = Column(Text, nullable=False, default="")

    # Pool management
    pool_version = Column(String, nullable=False, default="v2.0")
    used_count   = Column(Integer, nullable=False, default=0)  # how many sessions have drawn this case

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Evaluation(Base):
    """
    One row per operator × case decision.
    Primary outcome table.
    override = 1 when operator decision != algo_recommendation.
    """
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, autoincrement=True)

    operator_id  = Column(String, ForeignKey("operators.operator_id"), nullable=False, index=True)
    session_id   = Column(String, ForeignKey("operators.session_id"),  nullable=False, index=True)
    case_id      = Column(String, ForeignKey("vignettes.case_id"),     nullable=False, index=True)

    # Denormalised from Vignette for clean export (avoids joins in analysis)
    arm                 = Column(SAEnum(ArmEnum),                nullable=False)
    algo_recommendation = Column(SAEnum(AlgoRecommendationEnum), nullable=False)
    rule_result         = Column(SAEnum(RuleResultEnum),         nullable=False)

    # Operator inputs
    decision  = Column(SAEnum(DecisionEnum), nullable=True)   # null until submitted
    reasoning = Column(Text, nullable=True)                    # 1-2 lines, mandatory on submit

    # Derived outcome (set on submit)
    override = Column(Boolean, nullable=True)  # True if decision != algo_recommendation

    # Timing
    timestamp_open   = Column(DateTime(timezone=True), nullable=True)   # set when case loads
    timestamp_submit = Column(DateTime(timezone=True), nullable=True)   # set on submit
    response_time_sec = Column(Float, nullable=True)                    # derived: submit - open

    # Sequence within session (1–16)
    case_sequence = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("operator_id", "case_id", name="uq_operator_case"),
    )


class SurveyResponse(Base):
    """
    Post-task salience survey — submitted after all 16 cases.
    3 Likert items (1–5).
    """
    __tablename__ = "survey_responses"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    operator_id = Column(String, ForeignKey("operators.operator_id"), nullable=False, unique=True)
    session_id  = Column(String, ForeignKey("operators.session_id"),  nullable=False)

    # Q1: How much did field notes influence your decisions?
    salience_rating  = Column(Integer, nullable=False)  # 1–5

    # Q2: Did specific observations stand out?
    standout_rating  = Column(Integer, nullable=False)  # 1–5

    # Q3: How confident were you overall?
    confidence_rating = Column(Integer, nullable=False)  # 1–5

    submitted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SecondReview(Base):
    """
    Optional second-stage review.
    Triggered only for: arm=treatment AND override=True.
    Primary decision is hidden from secondary reviewer until they submit.
    """
    __tablename__ = "second_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)

    case_id              = Column(String, ForeignKey("vignettes.case_id"),     nullable=False, index=True)
    primary_operator_id  = Column(String, ForeignKey("operators.operator_id"), nullable=False)
    secondary_operator_id = Column(String, ForeignKey("operators.operator_id"), nullable=True)

    experience_gap  = Column(Integer,              nullable=True)   # secondary - primary experience_years
    review_type     = Column(SAEnum(ReviewTypeEnum), nullable=True)  # experienced / random

    # Primary decision stored here but NOT served to secondary reviewer
    # until secondary_decision is submitted (enforced at query layer)
    primary_decision   = Column(SAEnum(DecisionEnum), nullable=False)
    secondary_decision = Column(SAEnum(DecisionEnum), nullable=True)   # null until reviewed

    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at    = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("case_id", "primary_operator_id", name="uq_second_review_case_primary"),
    )


class AuditLog(Base):
    """
    Immutable audit trail for all significant system events.
    Replaces the v1.3 Event table (which had the .ts bug and mixed concerns).
    Never updated — append only.
    """
    __tablename__ = "audit_log"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    action      = Column(SAEnum(AuditActionEnum), nullable=False, index=True)
    actor_id    = Column(String, nullable=True, index=True)   # operator_id or "SYSTEM"
    session_id  = Column(String, nullable=True, index=True)
    case_id     = Column(String, nullable=True, index=True)
    payload     = Column(Text,   nullable=False, default="{}")  # JSON blob

    created_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)