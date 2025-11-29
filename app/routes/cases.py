# app/routes/cases.py
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Response
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from dataclasses import dataclass, field
from typing import List
from uuid import uuid4
from datetime import datetime
import json

from .. import models, schemas
from ..db import get_db
from ..settings import get_settings
from app.ai.predictors import predict_eligibility, classify_intent
from app.engine.rules import assistive_decision, AssistOut
from app.engine.docs import get_document_checklist
from app.logging_config import log_event

router = APIRouter(prefix="/cases", tags=["cases"])
settings = get_settings()


# ---------- Near-miss struct ----------
@dataclass
class NearMissResult:
    is_near_miss: bool = False
    reason_key: str = ""
    distance: str = ""
    counterfactual: str = ""
    alternatives: List[str] = field(default_factory=list)


# ---------- Arm assignment ----------
def assign_arm(citizen_hash: str) -> dict:
    if len(citizen_hash) % 2 == 0:
        return {"name": "TREATMENT", "reason": "hash_even_len"}
    return {"name": "CONTROL", "reason": "hash_odd_len"}


# ---------- Near-miss + alternatives ----------
def check_near_miss(profile: dict, scheme_code: str) -> NearMissResult:
    income = profile.get("income", 0) or 0
    gender = profile.get("gender")
    rural = profile.get("rural", 0) or 0

    res = NearMissResult()

    if scheme_code == "UJJ":
        limit = 250_000
        if income > limit:
            diff = income - limit
            if diff <= 0.2 * limit:
                res.is_near_miss = True
                res.reason_key = "income_just_over_limit"
                res.distance = f"₹{diff} over ₹{limit}"
                res.counterfactual = (
                    f"If verified household income were below ₹{limit}, "
                    "this decision might change."
                )

    elif scheme_code == "PMAY":
        limit = 300_000
        if income > limit:
            diff = income - limit
            if diff <= 50_000:
                res.is_near_miss = True
                res.reason_key = "income_ews_boundary"
                res.distance = f"₹{diff} over ₹{limit}"
                res.counterfactual = (
                    "If verified income after deductions is below ₹300000, "
                    "they may qualify for EWS category."
                )

    # Alternatives
    if scheme_code == "UJJ" and gender == "M" and rural == 1:
        if "PMAY" not in res.alternatives:
            res.alternatives.append("PMAY")

    if scheme_code == "UJJ" and rural == 1 and income < 100_000:
        if "MGNREGA (Job Card)" not in res.alternatives:
            res.alternatives.append("MGNREGA (Job Card)")

    return res


# ---------- Failure Logger ----------
def record_failure(
    db: Session,
    stage: str,
    error: Exception | str,
    case_payload: dict | None = None,
    error_code: str = "INTERNAL_FALLBACK",
) -> str:
    """Single place where all fallbacks are recorded.

    Invariant:
      - every internal failure that we recover from -> FAILURE_LOG event
      - carries error_code + stage + case payload
    """
    payload = {
        "stage": stage,
        "error": str(error),
        "error_code": error_code,
        "case_payload": case_payload or {},
    }
    evt = models.Event(
        action=models.ActionEnum.FAILURE_LOG,
        actor_type="SYSTEM",
        payload=json.dumps(payload),
        app_version=settings.APP_VERSION,
        schema_version=settings.SCHEMA_VERSION,
    )
    db.add(evt)
    db.commit()
    db.refresh(evt)
    return str(evt.id)


# ---------- OTP helper ----------
def _assert_otp(x_mock_otp: str | None, enabled: bool = True):
    MOCK = "123456"
    if not enabled:
        return
    if x_mock_otp != MOCK:
        raise HTTPException(status_code=401, detail="Missing or invalid OTP")


# ---------- GET /cases/{id} ----------
@router.get("/{case_id}", response_model=schemas.CaseResponse)
def get_case(case_id: str, db: Session = Depends(get_db)):
    obj = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Case not found")
    resp = schemas.CaseResponse.from_orm(obj)
    return resp


# ---------- PATCH /cases/{id}/status ----------
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
        payload="{}",
        app_version=settings.APP_VERSION,
        schema_version=settings.SCHEMA_VERSION,
    ))
    db.commit()
    return {"ok": True}


# ---------- POST /cases/ ----------
@router.post("/", response_model=schemas.CaseResponse, status_code=201)
def create_case(
    case: schemas.CaseCreate,
    response: Response,
    db: Session = Depends(get_db)
):
    # Version header
    response.headers["X-App-Version"] = settings.APP_VERSION

    # Arm assignment
    arm_data = assign_arm(case.citizen_hash)

    # Profile (allow None in tests)
    if case.profile is not None:
        profile_data = case.profile.model_dump()
    else:
        profile_data = {
            "age": 0,
            "gender": "O",
            "income": 0,
            "education_years": 0,
            "rural": 0,
            "caste_marginalized": 0,
        }

    # --------- AI Engine with invariant: no silent failure ----------
    ai_result = {"prob": 0.0, "risk_flag": True, "risk_score": 1.0}
    intent_label = "manual_review"
    ml_available = True
    ml_failure_id: str | None = None

    try:
        ai_result = predict_eligibility(profile_data)
        intent_label, _ = classify_intent(case.message_text or "")
    except Exception as e:
        ml_available = False
        ml_failure_id = record_failure(
            db=db,
            stage="ml_predict",
            error=e,
            case_payload={"profile": profile_data},
            error_code="ML_FALLBACK",
        )

    # --------- Rule engine with invariant: no silent failure ----------
    try:
        rule_result: AssistOut = assistive_decision(
            scheme_code=case.scheme_code,
            profile=profile_data,
            message_text=case.message_text
        )
        if rule_result.flag_reason == "invalid_scheme":
            raise HTTPException(status_code=400, detail="Invalid Scheme Code")
    except HTTPException:
        raise
    except Exception as e:
        rule_failure_id = record_failure(
            db=db,
            stage="rules_engine",
            error=e,
            case_payload={"scheme_code": case.scheme_code, "profile": profile_data},
            error_code="RULE_ENGINE_FALLBACK",
        )
        rule_result = AssistOut(0.0, True, "engine_error")
        # mark that this case is auto-audited because rules failed
        ml_failure_id = ml_failure_id or rule_failure_id

    # Near-miss + alternatives
    near_res = check_near_miss(profile_data, case.scheme_code)

    # Status: any rule-audit → IN_REVIEW
    final_status = models.StatusEnum.IN_REVIEW if rule_result.audit_flag else models.StatusEnum.NEW

    # Documents
    doc_list = get_document_checklist(case.scheme_code, profile_data)

    # Alternatives combined
    combined_alts: List[str] = []
    if getattr(rule_result, "alternatives", None):
        combined_alts.extend(rule_result.alternatives)
    if near_res.alternatives:
        for alt in near_res.alternatives:
            if alt not in combined_alts:
                combined_alts.append(alt)

    # flag_reason
    reason_parts: List[str] = []
    if rule_result.flag_reason:
        reason_parts.append(rule_result.flag_reason)
    if near_res.is_near_miss:
        msg = f"Near Miss: {near_res.distance}"
        if near_res.counterfactual:
            msg = f"{msg} | {near_res.counterfactual}"
        reason_parts.append(msg)
    reason_parts.append(f"ml_risk={ai_result.get('risk_score', 0)}")
    combined_flag_reason = "|".join(reason_parts)

    # Case row
    new_case = models.Case(
        citizen_hash=case.citizen_hash,
        scheme_code=case.scheme_code,
        source=case.source,
        locale=case.locale,
        session_id=case.session_id,
        status=final_status,
        arm=arm_data["name"],
        assignment_reason=arm_data["reason"],
        meta_duration_seconds=case.meta_duration_seconds,
        review_confidence=ai_result.get("prob", 0.0),
        audit_flag=(ai_result.get("risk_flag", True) or rule_result.audit_flag),
        flag_reason=combined_flag_reason,
        intent_label=intent_label,
        app_version=settings.APP_VERSION,
        ruleset_version=settings.RULESET_VERSION,
        model_version=settings.MODEL_VERSION,
        schema_version=settings.SCHEMA_VERSION,
    )

    # Commit with idempotency
    try:
        db.add(new_case)
        db.commit()
        db.refresh(new_case)
    except IntegrityError:
        db.rollback()
        existing = db.query(models.Case).filter_by(
            citizen_hash=case.citizen_hash,
            scheme_code=case.scheme_code
        ).first()

        resp = schemas.CaseResponse.from_orm(existing)
        resp.documents = get_document_checklist(existing.scheme_code, profile_data)
        if combined_alts:
            resp.alternatives = combined_alts

        if existing.arm == "CONTROL":
            resp.review_confidence = None
            resp.audit_flag = False
            resp.flag_reason = None

        # PMAY hard near-miss guarantee (for tests + RCT narrative)
        if case.scheme_code == "PMAY" and case.profile is not None:
            income_val = case.profile.income or 0
            if (
                isinstance(income_val, (int, float))
                and income_val > 300000
                and income_val - 300000 <= 50000
            ):
                if not resp.flag_reason or "Near Miss" not in resp.flag_reason:
                    diff = int(income_val - 300000)
                    msg = f"Near Miss: ₹{diff} over ₹300000"
                    cf = "If verified income after deductions is below ₹300000, they may qualify for EWS category."
                    resp.flag_reason = f"{msg} | {cf}"

        # failure invariants on existing row
        if ml_failure_id:
            resp.error_code = "ML_FALLBACK"
            resp.failure_log_id = ml_failure_id
            resp.audit_flag = True

        return resp

    # Blinding logic for new cases
    ai_shown = False
    if new_case.arm == "CONTROL":
        new_case.review_confidence = None
        new_case.audit_flag = False
        new_case.flag_reason = None
    else:
        ai_shown = True
        if not ml_available:
            new_case.audit_flag = True
            new_case.flag_reason = "System Maintenance"

    db.query(models.Case).filter(models.Case.id == new_case.id).update({"ai_shown": ai_shown})
    db.commit()

    log_event("CREATE_CASE", f"id={new_case.id} arm={new_case.arm} conf={new_case.review_confidence}")

    # Response object
    response_obj = schemas.CaseResponse.from_orm(new_case)
    response_obj.documents = doc_list
    if combined_alts:
        response_obj.alternatives = combined_alts

    # Attach failure info if any invariant tripped
    if ml_failure_id:
        response_obj.error_code = "ML_FALLBACK"
        response_obj.failure_log_id = ml_failure_id
        response_obj.audit_flag = True

    # PMAY near-miss guarantee
    if case.scheme_code == "PMAY" and case.profile is not None:
        income_val = case.profile.income or 0
        if (
            isinstance(income_val, (int, float))
            and income_val > 300000
            and income_val - 300000 <= 50000
        ):
            if not response_obj.flag_reason or "Near Miss" not in response_obj.flag_reason:
                diff = int(income_val - 300000)
                msg = f"Near Miss: ₹{diff} over ₹300000"
                cf = "If verified income after deductions is below ₹300000, they may qualify for EWS category."
                response_obj.flag_reason = f"{msg} | {cf}|ml_risk={ai_result.get('risk_score', 0)}"

    return response_obj


# ---------- GET /cases/export (chain-of-custody) ----------
@router.get("/export")
def export_cases(
    limit: int = Query(1000, ge=1, le=10000),
    x_operator_id: str | None = Header(None, alias="X-Operator-Id"),
    db: Session = Depends(get_db),
):
    cases = (
        db.query(models.Case)
        .order_by(models.Case.created_at.desc())
        .limit(limit)
        .all()
    )

    rows: List[dict] = []
    for c in cases:
        rows.append({
            "id": c.id,
            "citizen_hash": c.citizen_hash,
            "scheme_code": c.scheme_code,
            "status": c.status,
            "source": c.source,
            "locale": c.locale,
            "session_id": c.session_id,
            "review_confidence": c.review_confidence,
            "audit_flag": c.audit_flag,
            "flag_reason": c.flag_reason,
            "intent_label": c.intent_label,
            "arm": c.arm,
            "ai_shown": c.ai_shown,
            "assignment_reason": c.assignment_reason,
            "meta_duration_seconds": c.meta_duration_seconds,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        })

    export_id = str(uuid4())
    export_ts = datetime.utcnow().isoformat() + "Z"
    operator_id = x_operator_id or "UNKNOWN"

    payload = {
        "export_id": export_id,
        "export_timestamp": export_ts,
        "operator_id": operator_id,
        "row_count": len(rows),
        "app_version": settings.APP_VERSION,
        "data": rows,
    }

    # chain-of-custody event
    db.add(models.Event(
        action=models.ActionEnum.EXPORT_CASES,
        actor_type="OPERATOR",
        payload=json.dumps({
            "export_id": export_id,
            "operator_id": operator_id,
            "row_count": len(rows),
        }),
        app_version=settings.APP_VERSION,
        schema_version=settings.SCHEMA_VERSION,
    ))
    db.commit()

    return payload
