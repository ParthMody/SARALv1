# app/routes/cases.py
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.orm import Session
from .. import models, schemas
from ..db import get_db
# Import your new Engine functions
from app.ai.predictors import predict_eligibility, classify_intent
from app.engine.rules import assistive_decision
from app.logging_config import log_event
import os
import json

router = APIRouter(prefix="/cases", tags=["cases"])
MOCK = os.getenv("MOCK_OTP", "123456")

@router.post("/", response_model=schemas.CaseResponse, status_code=201)
def create_case(case: schemas.CaseCreate, db: Session = Depends(get_db)):
    scheme = db.query(models.Scheme).filter(models.Scheme.code == case.scheme_code).first()
    if not scheme:
        raise HTTPException(status_code=400, detail="Invalid scheme_code")

    # 1. Run the AI Engine (The "Shadow Validator")
    # Convert Pydantic model to dict for the engine
    profile_data = case.profile.model_dump()
    
    # A. Predict Eligibility (ML)
    ai_result = predict_eligibility(profile_data)
    # returns: {'label': 'likely', 'prob': 0.85, 'risk_flag': False, ...}

    # B. Run Heuristic Rules (Deterministic)
    rule_result = assistive_decision(
        {**case.model_dump(exclude={'profile'}), **profile_data}, 
        case.message_text
    )

    # C. Intent Classification (NLP)
    intent_label, _ = classify_intent(case.message_text or "")

    # 2. Save to Database
    new_case = models.Case(
        citizen_hash=case.citizen_hash,
        scheme_code=case.scheme_code,
        source=case.source,
        locale=case.locale,
        
        # Store the AI outputs
        review_confidence=ai_result['prob'], # Use the ML probability as confidence
        audit_flag=(ai_result['risk_flag'] or rule_result.audit_flag), # Union of flags
        flag_reason=f"{rule_result.flag_reason}|risk_score={ai_result['risk_score']}",
        intent_label=intent_label
    )
    
    # (Optional) You might want to store the input profile for future auditing
    # new_case.input_payload = json.dumps(profile_data) 

    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    log_event("CREATE_CASE", f"id={new_case.id} conf={new_case.review_confidence} flag={new_case.audit_flag}")
    
    return new_case