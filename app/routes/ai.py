# app/routes/ai.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from app.ai.ai_utils import assistive_score, classify_intent

router = APIRouter(prefix="/ai", tags=["ai"])

class AssistIn(BaseModel):
    scheme_code: str
    citizen_hash: str
    locale: str
    message_text: Optional[str] = None

@router.post("/assist")
def assist(inp: AssistIn):
    out = assistive_score(inp.model_dump(), inp.message_text)
    return {
        "review_confidence": out.review_confidence,
        "audit_flag": out.audit_flag,
        "flag_reason": out.flag_reason
    }

class IntentIn(BaseModel):
    text: str

@router.post("/classify")
def classify(inp: IntentIn):
    label, conf = classify_intent(inp.text)
    return {"label": label, "confidence": conf}