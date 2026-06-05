# app/models.py
"""
SARAL v2 Phase 2 — Data Model (Prolific deployment)

Tables:
  operators (participants)  — one row per session
  vignettes                 — pre-loaded pool (32 objects)
  evaluations               — primary outcome (one row per participant × case)
  survey_responses           — post-task survey
  audit_log                  — immutable event trail
"""
from __future__ import annotations

import enum
import uuid
import json
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Enum as SAEnum, ForeignKey, DateTime,
    Float, Boolean, Integer, Text, UniqueConstraint,
)
from sqlalchemy.sql import func
from sqlalchemy.types import TypeDecorator, TEXT

from .db import Base


# ─────────────────────────────────────────────
# SQLite-safe JSON helpers
# ─────────────────────────────────────────────

class JsonList(TypeDecorator):
    impl = TEXT
    cache_ok = True
    def process_bind_param(self, value, dialect):
        if value is None: return "[]"
        if isinstance(value, list): return json.dumps(value, ensure_ascii=False)
        if isinstance(value, str): return value.strip() or "[]"
        return "[]"
    def process_result_value(self, value, dialect):
        if not value: return []
        try:
            p = json.loads(value)
            return p if isinstance(p, list) else []
        except: return []


class JsonDict(TypeDecorator):
    impl = TEXT
    cache_ok = True
    def process_bind_param(self, value, dialect):
        if value is None: return "{}"
        if isinstance(value, dict): return json.dumps(value, ensure_ascii=False)
        if isinstance(value, str): return value.strip() or "{}"
        return "{}"
    def process_result_value(self, value, dialect):
        if not value: return {}
        try:
            p = json.loads(value)
            return p if isinstance(p, dict) else {}
        except: return {}


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
# Operator / Participant
# Table name kept as "operators" for backward compat
# ─────────────────────────────────────────────

class Operator(Base):
    __tablename__ = "operators"

    operator_id  = Column(String, primary_key=True, default=_uuid)
    session_id   = Column(String, nullable=False, unique=True, default=_uuid, index=True)

    # ── Prolific integration ──
    prolific_id  = Column(String, nullable=True, index=True)  # from URL param

    # ── Consent ──
    consent_given     = Column(Boolean, nullable=True)
    consent_timestamp = Column(DateTime(timezone=True), nullable=True)

    # ── Demographics (collected between consent and briefing) ──
    highest_education           = Column(String, nullable=True)
    occupation_category         = Column(String, nullable=True)
    public_admin_experience_years = Column(Integer, nullable=True)
    country_of_residence        = Column(String, nullable=True)

    # ── Legacy fields (kept for field-arm compat, optional for Prolific) ──
    initials         = Column(String(8),  nullable=True)
    age              = Column(Integer,    nullable=True)
    role             = Column(String(64), nullable=True)
    experience_years = Column(Integer,    nullable=True)

    # ── Session config ──
    locale           = Column(SAEnum(LocaleEnum), nullable=False, default=LocaleEnum.EN)
    status           = Column(SAEnum(SessionStatusEnum), nullable=False, default=SessionStatusEnum.IN_PROGRESS)
    cases_assigned   = Column(JsonList, default=list, nullable=False)
    list_assignment  = Column(String, nullable=True)
    case_order_seed  = Column(Integer, nullable=True)
    cases_completed  = Column(Integer, nullable=False, default=0)

    # ── Timestamps ──
    created_at               = Column(DateTime(timezone=True), server_default=func.now())
    completed_at             = Column(DateTime(timezone=True), nullable=True)
    session_start_timestamp  = Column(DateTime(timezone=True), nullable=True)
    session_end_timestamp    = Column(DateTime(timezone=True), nullable=True)

    # ── Metadata ──
    language_selected    = Column(String, nullable=True)
    instrument_version   = Column(String, nullable=True)
    session_complete     = Column(Boolean, nullable=False, default=False)

    # ── Quality control (Prolific) ──
    comprehension_failures  = Column(Integer, nullable=True, default=0)
    attention_check_passed  = Column(Boolean, nullable=True)
    prolific_completion_code = Column(String, nullable=True)
    completion_timestamp    = Column(DateTime(timezone=True), nullable=True)


# ─────────────────────────────────────────────
# Vignettes
# ─────────────────────────────────────────────

class Vignette(Base):
    __tablename__ = "vignettes"

    case_id             = Column(String, primary_key=True, default=_uuid)
    arm                 = Column(SAEnum(ArmEnum), nullable=False, index=True)
    algo_recommendation = Column(SAEnum(AlgoRecommendationEnum), nullable=False, index=True)
    rule_result         = Column(SAEnum(RuleResultEnum), nullable=False)
    profile_data        = Column(JsonDict, nullable=False, default=dict)
    field_note_en       = Column(Text, nullable=False, default="")
    field_note_mr       = Column(Text, nullable=False, default="")
    pool_version        = Column(String, nullable=False, default="v2.0")
    used_count          = Column(Integer, nullable=False, default=0)
    pair_id             = Column(Integer, nullable=True)
    list_assignment     = Column(String, nullable=True)
    created_at          = Column(DateTime(timezone=True), server_default=func.now())


# ─────────────────────────────────────────────
# Evaluations
# ─────────────────────────────────────────────

class Evaluation(Base):
    __tablename__ = "evaluations"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    operator_id  = Column(String, ForeignKey("operators.operator_id"), nullable=False, index=True)
    session_id   = Column(String, ForeignKey("operators.session_id"), nullable=False, index=True)
    case_id      = Column(String, ForeignKey("vignettes.case_id"), nullable=False, index=True)

    arm                 = Column(SAEnum(ArmEnum), nullable=False)
    algo_recommendation = Column(SAEnum(AlgoRecommendationEnum), nullable=False)
    rule_result         = Column(SAEnum(RuleResultEnum), nullable=False)

    decision  = Column(SAEnum(DecisionEnum), nullable=True)
    reasoning = Column(Text, nullable=True)
    override  = Column(Boolean, nullable=True)

    timestamp_open            = Column(DateTime(timezone=True), nullable=True)
    timestamp_submit          = Column(DateTime(timezone=True), nullable=True)
    response_time_sec         = Column(Float, nullable=True)
    time_to_first_action_ms   = Column(Integer, nullable=True)
    time_after_decision_ms    = Column(Integer, nullable=True)
    is_fast_response          = Column(Boolean, nullable=True)
    case_sequence             = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("operator_id", "case_id", name="uq_operator_case"),
    )


# ─────────────────────────────────────────────
# Survey Responses
# ─────────────────────────────────────────────

class SurveyResponse(Base):
    __tablename__ = "survey_responses"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    operator_id = Column(String, ForeignKey("operators.operator_id"), nullable=False, unique=True)
    session_id  = Column(String, ForeignKey("operators.session_id"), nullable=False)

    salience_rating   = Column(Integer, nullable=False)
    standout_rating   = Column(Integer, nullable=False)
    confidence_rating = Column(Integer, nullable=False)
    feedback          = Column(Text, nullable=True)

    submitted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# ─────────────────────────────────────────────
# Audit Log
# ─────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_log"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    action     = Column(SAEnum(AuditActionEnum), nullable=False, index=True)
    actor_id   = Column(String, nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    case_id    = Column(String, nullable=True, index=True)
    payload    = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)