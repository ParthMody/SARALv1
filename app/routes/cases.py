# app/routes/cases.py
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Response
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
from .. import models, schemas
from ..db import get_db
from ..settings import get_settings
from app.ai.predictors import predict_eligibility, classify_intent
from app.engine.rules import assistive_decision
from app.logging_config import log_event
from app.engine.docs import get_document_checklist

router = APIRouter(prefix="/cases", tags=["cases"])
settings = get_settings()

# --- THREAT MODEL: VELOCITY CHECK ---
def check_gaming_attempt(db: Session, citizen_hash: str) -> bool:
    """
    Detects if an operator is spamming inputs for the same citizen 
    to 'guess' the right answer.
    """
    window = datetime.utcnow() - timedelta(minutes=settings.RETRY_WINDOW_MINUTES)
    count = db.query(models.Case).filter(
        models.Case.citizen_hash == citizen_hash,
        models.Case.created_at >= window
    ).count()
    return count >= settings.MAX_RETRY_COUNT

def assign_arm(citizen_hash: str) -> str:
    if len(citizen_hash) % 2 == 0: return "TREATMENT"
    return "CONTROL"

@router.post("/", response_model=schemas.CaseResponse, status_code=201)
def create_case(
    case: schemas.CaseCreate, 
    response: Response, 
    db: Session = Depends(get_db)
):
    # 0. Version Header (Reproducibility)
    response.headers["X-App-Version"] = settings.APP_VERSION
    response.headers["X-Model-Version"] = settings.MODEL_VERSION

    # 1. Threat Check
    if check_gaming_attempt(db, case.citizen_hash):
        log_event("SECURITY_FLAG", f"Gaming attempt detected for {case.citizen_hash}")
        # We don't block them (to avoid confrontation), but we force a flag
        force_audit = True 
    else:
        force_audit = False

    # 2. Check Scheme
    scheme = db.query(models.Scheme).filter(models.Scheme.code == case.scheme_code).first()
    if not scheme: raise HTTPException(400, "Invalid scheme")

    # 3. Core Logic
    arm = assign_arm(case.citizen_hash)
    profile_data = case.profile.model_dump()
    
    # AI Engine
    try:
        ai_result = predict_eligibility(profile_data)
        intent_label, _ = classify_intent(case.message_text or "")
    except Exception as e:
        # FALLBACK PATH (Failure Domain B)
        print(f"⚠️ AI FAIL: {e}")
        ai_result = {"prob": 0.0, "risk_flag": True, "risk_score": 1.0} 
        intent_label = "sys_error"

    # Rule Engine
    try:
        rule_result = assistive_decision({**case.model_dump(exclude={'profile'}), **profile_data}, case.message_text)
    except:
        from app.engine.rules import AssistOut
        rule_result = AssistOut(review_confidence=0.0, audit_flag=True, flag_reason="engine_error")

    doc_list = get_document_checklist(case.scheme_code, profile_data)

    # 4. Save Case
    new_case = models.Case(
        citizen_hash=case.citizen_hash,
        scheme_code=case.scheme_code,
        source=case.source,
        locale=case.locale,
        arm=arm,
        # TELEMETRY: Capture the duration sent by frontend
        meta_duration_seconds=0, # TODO: Add this to Schema if not already present
        
        # AI Data
        review_confidence=ai_result.get('prob', 0.0), 
        audit_flag=(ai_result.get('risk_flag', True) or rule_result.audit_flag or force_audit),
        flag_reason=f"{rule_result.flag_reason}|risk={ai_result.get('risk_score',0)}|gaming={force_audit}",
        intent_label=intent_label,
    )

    try:
        db.add(new_case)
        db.commit()
        db.refresh(new_case)
    except IntegrityError:
        db.rollback()
        existing = db.query(models.Case).filter_by(citizen_hash=case.citizen_hash, scheme_code=case.scheme_code).first()
        # Blinding for existing
        if existing and existing.arm == "CONTROL":
            existing.review_confidence = None
            existing.audit_flag = False
        resp = schemas.CaseResponse.from_orm(existing)
        resp.documents = get_document_checklist(existing.scheme_code, profile_data)
        return resp

    # 5. Blinding
    if new_case.arm == "CONTROL":
        new_case.review_confidence = None
        new_case.audit_flag = False

    log_event("CREATE_CASE", f"id={new_case.id} arm={arm} conf={new_case.review_confidence}")
    
    resp = schemas.CaseResponse.from_orm(new_case)
    resp.documents = doc_list
    return resp

# ... keep existing update_status ...
def _assert_otp(x_mock_otp: str | None, enabled: bool = True):
    if not enabled: return
    if x_mock_otp != settings.MOCK_OTP: raise HTTPException(401, "Invalid OTP")

@router.patch("/{case_id}/status")
def update_status(case_id: str, status: str = Query(...), x_mock_otp: str | None = Header(None, alias="X-Mock-OTP"), db: Session = Depends(get_db)):
    _assert_otp(x_mock_otp)
    obj = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not obj: raise HTTPException(404, "Not found")
    obj.status = status
    db.commit()
    log_event("UPDATE_STATUS", f"id={obj.id} status={obj.status}")
    db.add(models.Event(case_id=obj.id, action=models.ActionEnum.UPDATE_STATUS, actor_type="OPERATOR", payload="{}"))
    db.commit()
    return {"ok": True}