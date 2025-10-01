from sqlalchemy import Column, String, Enum, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func
import uuid, enum
from .db import Base

# Cross-DB UUID type (works on SQLite & Postgres)
try:
    from sqlalchemy import Uuid  # SQLAlchemy 2.0
    UUIDType = Uuid
except Exception:
    from sqlalchemy.types import CHAR
    from sqlalchemy.dialects.postgresql import UUID
    UUIDType = UUID if UUID else CHAR(36)

class StatusEnum(str, enum.Enum):
    NEW = "NEW"; IN_REVIEW = "IN_REVIEW"; APPROVED = "APPROVED"; REJECTED = "REJECTED"

class SourceEnum(str, enum.Enum):
    SMS = "SMS"; WEB = "WEB"

class ActionEnum(str, enum.Enum):
    CREATE_CASE = "CREATE_CASE"; UPDATE_STATUS = "UPDATE_STATUS"; LOGIN = "LOGIN"

class ActorEnum(str, enum.Enum):
    CITIZEN = "CITIZEN"; OPERATOR = "OPERATOR"; SYSTEM = "SYSTEM"

class Scheme(Base):
    __tablename__ = "schemes"
    code = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)

class Case(Base):
    __tablename__ = "cases"
    id = Column(UUIDType(as_uuid=True) if UUIDType.__name__ == "UUID" else String, primary_key=True,
                default=lambda: str(uuid.uuid4()))
    citizen_hash = Column(String, nullable=False, index=True)
    scheme_code = Column(String, ForeignKey("schemes.code"), nullable=False)
    status = Column(Enum(StatusEnum), nullable=False, default=StatusEnum.NEW)
    source = Column(Enum(SourceEnum), nullable=False)
    locale = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Event(Base):
    __tablename__ = "events"
    id = Column(UUIDType(as_uuid=True) if UUIDType.__name__ == "UUID" else String, primary_key=True,
                default=lambda: str(uuid.uuid4()))
    case_id = Column(String, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    action = Column(Enum(ActionEnum), nullable=False)
    actor_type = Column(String, nullable=False)  # keep simple for v1; can enum later
    actor_id = Column(String, nullable=True)
    payload = Column(String)  # JSON string for SQLite compatibility
    ts = Column(DateTime(timezone=True), server_default=func.now())