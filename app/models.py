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
)
from sqlalchemy.sql import func
from sqlalchemy.types import TypeDecorator, TEXT

from .db import Base


# -------------------------
# SQLite-safe JSON list
# -------------------------
class JsonList(TypeDecorator):
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


class StatusEnum(str, enum.Enum):
    NEW = "NEW"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class SourceEnum(str, enum.Enum):
    SMS = "SMS"
    WEB = "WEB"
    KIOSK_CHAT = "KIOSK_CHAT"


class ActionEnum(str, enum.Enum):
    CREATE_CASE = "CREATE_CASE"
    UPDATE_STATUS = "UPDATE_STATUS"
    EXPORT_CASES = "EXPORT_CASES"
    FAILURE_LOG = "FAILURE_LOG"
    ASSIGN_ARM = "ASSIGN_ARM"
    OP_DISPOSITION = "OP_DISPOSITION"
    OPEN_CASE = "OPEN_CASE"


class RuleResultEnum(str, enum.Enum):
    ELIGIBLE_BY_RULE = "ELIGIBLE_BY_RULE"
    INELIGIBLE_BY_RULE = "INELIGIBLE_BY_RULE"
    UNKNOWN_NEEDS_DOCS = "UNKNOWN_NEEDS_DOCS"


# SOP decision states (publishable)
class FinalActionEnum(str, enum.Enum):
    APPROVE = "APPROVE"
    REQUEST_DOCS = "REQUEST_DOCS"
    ESCALATE = "ESCALATE"
    REJECT = "REJECT"


class ReasonCodeEnum(str, enum.Enum):
    RULE_FAIL = "RULE_FAIL"
    DOCS_MISSING = "DOCS_MISSING"
    MISMATCH = "MISMATCH"
    FRAUD_SUSPECTED = "FRAUD_SUSPECTED"
    OTHER = "OTHER"


def _uuid() -> str:
    return str(uuid.uuid4())


class Scheme(Base):
    __tablename__ = "schemes"
    code = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)


class Case(Base):
    __tablename__ = "cases"

    id = Column(String, primary_key=True, default=_uuid)

    citizen_hash = Column(String, nullable=False, index=True)
    scheme_code = Column(String, ForeignKey("schemes.code"), nullable=False)

    status = Column(SAEnum(StatusEnum), nullable=False, default=StatusEnum.NEW)
    source = Column(SAEnum(SourceEnum), nullable=False)
    locale = Column(String, nullable=False)

    # Session / telemetry (keep)
    session_id = Column(String, index=True, nullable=True)
    meta_duration_seconds = Column(Integer, nullable=True)

    # RCT
    arm = Column(String, nullable=False)  # CONTROL / TREATMENT
    assignment_reason = Column(String, nullable=True)

    # IMPORTANT: proves score existed but was/wasn't exposed
    decision_support_shown = Column(Boolean, default=False)

    # BAU rules instrument (shown in BOTH arms)
    rule_result = Column(SAEnum(RuleResultEnum), nullable=True)
    rule_reasons = Column(JsonList, default=list, nullable=False)
    documents = Column(JsonList, default=list, nullable=False)

    # ML (computed for all; shown only for TREATMENT)
    review_confidence = Column(Float, nullable=True)  # e.g., P(eligible)
    risk_score = Column(Float, nullable=True)         # 1 - confidence
    risk_band = Column(String, nullable=True)         # LOW / MED / HIGH
    top_reasons = Column(JsonList, default=list, nullable=False)

    # Safety gate (route to review), never auto-reject
    audit_flag = Column(Boolean, default=False)

    # Operator process
    opened_at = Column(DateTime(timezone=True), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    operator_id = Column(String, nullable=True)
    sop_version = Column(String, nullable=True)

    # Outcome
    final_action = Column(SAEnum(FinalActionEnum), nullable=True)
    reason_code = Column(SAEnum(ReasonCodeEnum), nullable=True)

    # Treatment-only metric (operator went against risk gate / recommendation)
    override_flag = Column(Boolean, nullable=True)

    # Provenance (keep)
    app_version = Column(String, nullable=True)
    ruleset_version = Column(String, nullable=True)
    model_version = Column(String, nullable=True)
    schema_version = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)

    case_id = Column(String, nullable=True, index=True)
    action = Column(SAEnum(ActionEnum), nullable=False)
    actor_type = Column(String, default="SYSTEM")
    payload = Column(Text, default="{}")

    app_version = Column(String, default="dev")
    schema_version = Column(String, default="dev")

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
