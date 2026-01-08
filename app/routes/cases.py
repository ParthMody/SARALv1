# app/routes/cases.py
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.inspection import inspect as sa_inspect
from sqlalchemy.orm import Session

from app import models, schemas
from app.ai.predictors import predict_eligibility
from app.db import get_db
from app.engine.docs import get_document_checklist
from app.engine.rules import assistive_decision
from app.engine.scheme_config import get_scheme_config
from app.settings import get_settings

router = APIRouter(prefix="/cases", tags=["cases"])
settings = get_settings()


# -------------------------------------------------------------------
# RCT ASSIGNMENT
# -------------------------------------------------------------------
@dataclass(frozen=True)
class ArmAssignment:
    name: str
    reason: str


def assign_arm(citizen_hash: str, scheme_code: str) -> ArmAssignment:
    salt = getattr(settings, "RCT_SALT", "dev_salt_change_me")
    key = f"{citizen_hash}|{scheme_code}|{salt}"
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    arm = "TREATMENT" if int(h, 16) % 2 == 0 else "CONTROL"
    return ArmAssignment(name=arm, reason=f"sha256_parity:{h[:12]}")


# -------------------------------------------------------------------
# EVENT LOGGING
# -------------------------------------------------------------------
def _event_kwargs_safe(extra: dict[str, Any]) -> dict[str, Any]:
    """
    Event schema varies across your iterations.
    Only pass columns that exist on models.Event to avoid TypeError.
    """
    try:
        cols = {c.key for c in sa_inspect(models.Event).mapper.column_attrs}
    except Exception:
        cols = set()

    out: dict[str, Any] = {}
    for k, v in extra.items():
        if not cols or k in cols:
            out[k] = v
    return out


def record_event(
    db: Session,
    action: models.ActionEnum,
    case_id: str | None,
    payload: dict[str, Any],
    *,
    verification_status: models.VerificationStatusEnum | None = None,
    verification_note: str | None = None,
):
    base = dict(
        case_id=case_id,
        action=action,
        actor_type="SYSTEM",
        payload=json.dumps(payload, ensure_ascii=False),
        app_version=settings.APP_VERSION,
        schema_version=settings.SCHEMA_VERSION,
    )

    extra = {}
    if verification_status is not None:
        extra["verification_status"] = verification_status
    if verification_note is not None:
        extra["verification_note"] = verification_note

    evt = models.Event(**base, **_event_kwargs_safe(extra))
    db.add(evt)
    db.commit()


def record_failure(
    db: Session,
    stage: str,
    error: Exception | str,
    case_payload: dict | None = None,
    error_code: str = "INTERNAL_FALLBACK",
) -> str:
    evt = models.Event(
        action=models.ActionEnum.FAILURE_LOG,
        actor_type="SYSTEM",
        payload=json.dumps(
            {
                "stage": stage,
                "error": str(error),
                "error_code": error_code,
                "case_payload": case_payload or {},
            },
            ensure_ascii=False,
        ),
        app_version=settings.APP_VERSION,
        schema_version=settings.SCHEMA_VERSION,
    )
    db.add(evt)
    db.commit()
    db.refresh(evt)
    return str(evt.id)


def _risk_band(risk: float) -> str:
    if risk >= 0.7:
        return "HIGH"
    if risk >= 0.4:
        return "MED"
    return "LOW"


def _case_kwargs_safe(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Your DB shows cases table does NOT currently have verification_* columns.
    Filter kwargs to only Case columns to prevent:
      TypeError: 'verification_status' is an invalid keyword argument for Case
    """
    cols = {c.key for c in sa_inspect(models.Case).mapper.column_attrs}
    return {k: v for k, v in raw.items() if k in cols}


# -------------------------------------------------------------------
# CREATE CASE
# -------------------------------------------------------------------
@router.post("/", response_model=schemas.CaseResponse, status_code=201)
def create_case(
    case: schemas.CaseCreate,
    response: Response,
    db: Session = Depends(get_db),
):
    response.headers["X-App-Version"] = settings.APP_VERSION

    cfg = get_scheme_config(case.scheme_code)
    if not cfg:
        raise HTTPException(400, "Invalid scheme")

    profile = case.profile.model_dump()

    # -----------------------------
    # Verification normalization
    # -----------------------------
    try:
        verification_status = models.VerificationStatusEnum(case.verification_status)
    except Exception:
        verification_status = models.VerificationStatusEnum.NO_ID_PRESENTED

    verification_note = case.verification_note

    # -----------------------------
    # RCT Arm Assignment
    # -----------------------------
    arm = assign_arm(case.citizen_hash, case.scheme_code)
    record_event(
        db,
        models.ActionEnum.ASSIGN_ARM,
        None,
        {"arm": arm.name, "reason": arm.reason},
        verification_status=verification_status,
        verification_note=verification_note,
    )

    # -----------------------------
    # RULE ENGINE (HARDENED)
    # -----------------------------
    rule_out = assistive_decision(case.scheme_code, profile)

    raw_rr = getattr(rule_out, "rule_result", None)
    if hasattr(raw_rr, "value"):
        rr_str = raw_rr.value
    elif isinstance(raw_rr, str):
        rr_str = raw_rr
    else:
        rr_str = models.RuleResultEnum.UNKNOWN_NEEDS_DOCS.value

    try:
        rule_result_enum = models.RuleResultEnum(rr_str)
    except Exception:
        rule_result_enum = models.RuleResultEnum.UNKNOWN_NEEDS_DOCS

    rule_reasons = list(getattr(rule_out, "reasons", None) or [])
    documents = get_document_checklist(case.scheme_code, profile)

    # -----------------------------
    # ML (always computed, selectively shown)
    # -----------------------------
    ml_available = True
    ml_failure_id: str | None = None

    review_confidence = 0.0
    risk_score = 1.0
    top_reasons: list[str] = []

    try:
        ai = predict_eligibility(profile) or {}
        review_confidence = float(ai.get("prob", 0.0))
        review_confidence = max(0.0, min(1.0, review_confidence))
        risk_score = 1.0 - review_confidence

        tr = ai.get("top_reasons", []) or []
        if not isinstance(tr, list):
            tr = []
        top_reasons = [str(x) for x in tr][:5]
    except Exception as e:
        ml_available = False
        ml_failure_id = record_failure(
            db,
            "ml_predict",
            e,
            {"profile": profile},
            "ML_FALLBACK",
        )
        risk_score = 1.0
        review_confidence = 0.0
        top_reasons = ["ML unavailable"]

    risk_band = _risk_band(risk_score)
    audit_flag = (not ml_available) or (risk_score >= 0.7)

    status = (
        models.StatusEnum.IN_REVIEW
        if rule_result_enum != models.RuleResultEnum.ELIGIBLE_BY_RULE or audit_flag
        else models.StatusEnum.NEW
    )

    # -----------------------------
    # SOURCE NORMALIZATION
    # -----------------------------
    try:
        source = models.SourceEnum(case.source)
    except Exception:
        source = models.SourceEnum.KIOSK_CHAT

    # -----------------------------
    # CREATE CASE ROW (SAFE AGAINST SCHEMA DRIFT)
    # -----------------------------
    raw_case_kwargs: dict[str, Any] = dict(
        citizen_hash=case.citizen_hash,
        scheme_code=case.scheme_code,
        source=source,
        locale=case.locale,
        session_id=case.session_id,
        meta_duration_seconds=case.meta_duration_seconds,
        status=status,
        arm=arm.name,
        assignment_reason=arm.reason,
        decision_support_shown=(arm.name == "TREATMENT"),
        rule_result=rule_result_enum,
        rule_reasons=rule_reasons,
        documents=documents,
        review_confidence=review_confidence,
        risk_score=risk_score,
        risk_band=risk_band,
        top_reasons=top_reasons,
        audit_flag=audit_flag,
        sop_version="SOP_v1",
        app_version=settings.APP_VERSION,
        ruleset_version=cfg.get("ruleset_version") or getattr(settings, "RULESET_VERSION", "dev"),
        model_version=getattr(settings, "MODEL_VERSION", "dev"),
        schema_version=settings.SCHEMA_VERSION,
        # Optional future columns (will be silently ignored if not in DB):
        profile_data=profile,
        verification_status=verification_status,
        verification_note=verification_note,
    )

    new_case = models.Case(**_case_kwargs_safe(raw_case_kwargs))

    try:
        db.add(new_case)
        db.commit()
        db.refresh(new_case)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Duplicate insert")

    record_event(
        db,
        models.ActionEnum.CREATE_CASE,
        str(new_case.id),
        {
            "arm": arm.name,
            "decision_support_shown": bool(getattr(new_case, "decision_support_shown", False)),
            "risk_score": getattr(new_case, "risk_score", None),
            "risk_band": getattr(new_case, "risk_band", None),
            "audit_flag": bool(getattr(new_case, "audit_flag", False)),
            "rule_result": getattr(getattr(new_case, "rule_result", None), "value", str(getattr(new_case, "rule_result", ""))),
            "ml_available": ml_available,
            "ml_failure_id": ml_failure_id,
            "verification_status": verification_status.value,
        },
        verification_status=verification_status,
        verification_note=verification_note,
    )

    resp = schemas.CaseResponse.model_validate(new_case)

    # -----------------------------
    # CONTROL ARM BLINDING
    # -----------------------------
    if getattr(new_case, "arm", None) == "CONTROL":
        resp.review_confidence = None
        resp.risk_score = None
        resp.risk_band = None
        resp.top_reasons = []
        resp.decision_support_shown = False
        resp.audit_flag = None
        resp.override_flag = None

    return resp
