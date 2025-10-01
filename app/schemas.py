from pydantic import BaseModel
from datetime import datetime
from enum import Enum

class StatusEnum(str, Enum):
    NEW = "NEW"; IN_REVIEW = "IN_REVIEW"; APPROVED = "APPROVED"; REJECTED = "REJECTED"

class CaseCreate(BaseModel):
    citizen_hash: str
    scheme_code: str
    source: str
    locale: str

class CaseResponse(BaseModel):
    id: str
    scheme_code: str
    status: StatusEnum
    locale: str
    created_at: datetime

    class Config:
        from_attributes = True  # Pydantic v2