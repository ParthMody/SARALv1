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
# SQLite-safe JSON Types
# -------------------------
class JsonList(TypeDecorator):
    """
    Saves a list of strings/objects as a JSON array string in the DB.
    Returns a Python list when queried.
    """
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
    """
    Saves a dictionary as a JSON object string in the DB.
    Returns a Python dict when queried. 
    Crucial for 'profile_data'.
    """
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


# -------------------------
# Enums
# -------------------------

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


# Verification Modality (The "Zero Docs" Logic)
class VerificationStatusEnum(str, enum.Enum):
    ID_PHOTO_UPLOADED = "ID_PHOTO_UPLOADED"
    ID_SEEN_PHYSICAL = "ID_SEEN_PHYSICAL"
    NO_ID_PRESENTED = "NO_ID_PRESENTED"


# SOP decision states
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


# -------------------------
# Models
# -------------------------

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

    # Telemetry
    session_id = Column(String, index=True, nullable=True)
    meta_duration_seconds = Column(Integer, nullable=True)

    # RCT Configuration
    arm = Column(String, nullable=False)  # CONTROL / TREATMENT
    assignment_reason = Column(String, nullable=True)
    decision_support_shown = Column(Boolean, default=False)

    # Input Data
    profile_data = Column(JsonDict, default=dict, nullable=False) # Stores Age, Income, Gender
    documents = Column(JsonList, default=list, nullable=False)    # Stores file paths

    # Rules Engine (BAU)
    rule_result = Column(SAEnum(RuleResultEnum), nullable=True)
    rule_reasons = Column(JsonList, default=list, nullable=False)

    # ML Output (Treatment Only)
    review_confidence = Column(Float, nullable=True)  # P(eligible)
    risk_score = Column(Float, nullable=True)         # 1 - confidence
    risk_band = Column(String, nullable=True)         # LOW / HIGH
    top_reasons = Column(JsonList, default=list, nullable=False)
    audit_flag = Column(Boolean, default=False)

    # Verification (The "Zero Docs" fix)
    verification_status = Column(
        SAEnum(VerificationStatusEnum),
        nullable=False,
        default=VerificationStatusEnum.NO_ID_PRESENTED,
    )
    verification_note = Column(Text, nullable=True)

    # Operator Process (The "Hidden Stopwatch")
    # opened_at: Set by JS when the eye hits the row
    # decided_at: Set by backend when the button is clicked
    opened_at = Column(DateTime(timezone=True), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    operator_id = Column(String, nullable=True)
    sop_version = Column(String, nullable=True)

    # Outcomes
    final_action = Column(SAEnum(FinalActionEnum), nullable=True)
    reason_code = Column(SAEnum(ReasonCodeEnum), nullable=True)
    override_flag = Column(Boolean, nullable=True)

    # Provenance
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