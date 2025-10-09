# app/routes/cases.py
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.orm import Session
from .. import models, schemas
from ..db import get_db
from app.ai.ai_utils import assistive_score, classify_intent
import os

router = APIRouter(prefix="/cases", tags=["cases"])
MOCK = os.getenv("MOCK_OTP", "123456")

@router.post("/", response_model=schemas.CaseResponse, status_code=201)
def create_case(case: schemas.CaseCreate, db: Session = Depends(get_db)):
    scheme = db.query(models.Scheme).filter(models.Scheme.code == case.scheme_code).first()
    if not scheme:
        raise HTTPException(status_code=400, detail="Invalid scheme_code")

    new_case = models.Case(
        citizen_hash=case.citizen_hash,
        scheme_code=case.scheme_code,
        source=case.source,
        locale=case.locale,
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    # Assistive AI (ethical, explainable)
    message_text = "apply gas connection"  # replace with real SMS text when available
    assist = assistive_score(
        {"scheme_code": new_case.scheme_code, "citizen_hash": new_case.citizen_hash, "locale": new_case.locale},
        message_text
    )
    new_case.review_confidence = assist.review_confidence
    new_case.audit_flag = assist.audit_flag
    new_case.flag_reason = assist.flag_reason

    # Optional: intent label
    label, _ = classify_intent(message_text)
    new_case.intent_label = label

    db.commit()
    db.refresh(new_case)

    # Log CREATE_CASE
    db.add(models.Event(
        case_id=new_case.id,
        action=models.ActionEnum.CREATE_CASE,
        actor_type="CITIZEN",
        payload="{}"
    ))
    db.commit()
    return new_case

def _assert_otp(x_mock_otp: str | None, enabled: bool = True):
    if not enabled:
        return
    if x_mock_otp != MOCK:
        raise HTTPException(status_code=401, detail="Missing or invalid OTP")

@router.patch("/{case_id}/status")
def update_status(
    case_id: str,
    status: str = Query(..., description="NEW | IN_REVIEW | APPROVED | REJECTED"),
    x_mock_otp: str | None = Header(None, alias="X-Mock-OTP"),
    db: Session = Depends(get_db),
):
    _assert_otp(x_mock_otp)
    obj = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Case not found")
    allowed = [s.value for s in models.StatusEnum]
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {allowed}")
    obj.status = status
    db.commit()
    db.refresh(obj)

    db.add(models.Event(
        case_id=obj.id,
        action=models.ActionEnum.UPDATE_STATUS,
        actor_type="OPERATOR",
        payload="{}"
    ))
    db.commit()
    return {"ok": True}
