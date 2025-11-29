# app/models.py
from sqlalchemy import Column, String, Enum as SAEnum, ForeignKey, DateTime, Float, Boolean, Integer, UniqueConstraint, Text
from sqlalchemy.sql import func
import uuid, enum
from .db import Base

class StatusEnum(str, enum.Enum):
    NEW = "NEW"; IN_REVIEW = "IN_REVIEW"; APPROVED = "APPROVED"; REJECTED = "REJECTED"

class SourceEnum(str, enum.Enum):
    SMS = "SMS"; WEB = "WEB"; KIOSK_CHAT = "KIOSK_CHAT"

class ActionEnum(str, enum.Enum):
    CREATE_CASE = "CREATE_CASE"; UPDATE_STATUS = "UPDATE_STATUS"; LOGIN = "LOGIN"
    # Telemetry Events
    FORM_STARTED = "FORM_STARTED"; NEAR_MISS_SHOWN = "NEAR_MISS_SHOWN"
    ML_FALLBACK = "ML_FALLBACK"; OP_OVERRIDE = "OP_OVERRIDE"; ASSIGN_ARM = "ASSIGN_ARM"

class Scheme(Base):
    __tablename__ = "schemes"
    code = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)

def _uuid() -> str: return str(uuid.uuid4())

class Case(Base):
    __tablename__ = "cases"
    id = Column(String, primary_key=True, default=_uuid) 
    citizen_hash = Column(String, nullable=False, index=True)
    scheme_code = Column(String, ForeignKey("schemes.code"), nullable=False)
    status = Column(SAEnum(StatusEnum), nullable=False, default=StatusEnum.NEW)
    source = Column(SAEnum(SourceEnum), nullable=False)
    locale = Column(String, nullable=False)
    
    # Session Persistence
    session_id = Column(String, index=True, nullable=True)
    
    # AI & Decision Fields
    review_confidence = Column(Float, nullable=True)   
    audit_flag = Column(Boolean, default=False)
    flag_reason = Column(String, nullable=True)       
    intent_label = Column(String, nullable=True)
    
    # Experimental Telemetry
    arm = Column(String, nullable=True) 
    ai_shown = Column(Boolean, default=False)
    assignment_reason = Column(String, nullable=True)
    
    # Outcome Metrics
    meta_duration_seconds = Column(Integer, nullable=True)
    
    # --- VERSIONING (Provenance) ---
    app_version = Column(String, nullable=True)
    ruleset_version = Column(String, nullable=True)
    model_version = Column(String, nullable=True)
    schema_version = Column(String, nullable=True) # <--- THIS WAS MISSING

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('citizen_hash', 'scheme_code', name='uix_citizen_scheme'),
    )

class Event(Base):
    __tablename__ = "events"
    id = Column(String, primary_key=True, default=_uuid)
    case_id = Column(String, ForeignKey("cases.id", ondelete="CASCADE"), nullable=True)
    session_id = Column(String, nullable=True)
    action = Column(SAEnum(ActionEnum), nullable=False)
    actor_type = Column(String, nullable=False) 
    payload = Column(Text)
    ts = Column(DateTime(timezone=True), server_default=func.now())
    app_version = Column(String, nullable=True)

class ActionEnum(str, enum.Enum):
    ML_FALLBACK = "ML_FALLBACK"
    UPDATE_STATUS = "UPDATE_STATUS"
    EXPORT_CASES = "EXPORT_CASES"
    FAILURE_LOG = "FAILURE_LOG"  