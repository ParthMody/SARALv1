# app/routes/cases.py
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from ..settings import get_settings

from app.ai.predictors import predict_eligibility
from app.engine.rules import assistive_decision
from app.engine.scheme_config import get_scheme_config
from app.engine.docs import get_document_checklist

router = APIRouter(prefix="/cases", tags=["cases"])
settings = get_settings()


# -------------------------
# RCT ASSIGNMENT
# -------------------------
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


# -------------------------
# EVENTS / FAILURE LOGGING
# -------------------------
def record_event(db: Session, action: models.ActionEnum, case_id: str | None, payload: dict):
    evt = models.Event(
        case_id=case_id,
        action=action,
        actor_type="SYSTEM",
        payload=json.dumps(payload, ensure_ascii=False),
        app_version=settings.APP_VERSION,
        schema_version=settings.SCHEMA_VERSION,
    )
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
        payload=json.dumps({
            "stage": stage,
            "error": str(error),
            "error_code": error_code,
            "case_payload": case_payload or {},
        }, ensure_ascii=False),
        app_version=settings.APP_VERSION,
        schema_version=settings.SCHEMA_VERSION,
    )
    db.add(evt)
    db.commit()
    db.refresh(evt)
    return str(evt.id)


def _risk_band(risk: float) -> str:
    return "HIGH" if risk >= 0.7 else "MED" if risk >= 0.4 else "LOW"


# -------------------------
# EXPORT
# -------------------------
@router.get("/export.csv")
def export_cases_csv(
    min_risk: float = Query(0.0, ge=0.0, le=1.0),
    since: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Case)

    if since:
        try:
            q = q.filter(models.Case.created_at >= datetime.strptime(since, "%Y-%m-%d"))
        except ValueError:
            raise HTTPException(400, "Invalid date format (use YYYY-MM-DD)")

    if min_risk > 0:
        q = q.filter(models.Case.risk_score.isnot(None), models.Case.risk_score >= min_risk)

    rows = q.order_by(models.Case.created_at.desc()).all()

    buf = StringIO()
    w = csv.writer(buf)
    w.writerow([
        "id", "scheme_code", "status", "source", "locale",
        "arm", "assignment_reason", "decision_support_shown",
        "rule_result", "rule_reasons", "documents",
        "review_confidence", "risk_score", "risk_band", "top_reasons",
        "audit_flag",
        "final_action", "reason_code", "override_flag",
        "opened_at", "decided_at", "operator_id", "sop_version",
        "session_id", "meta_duration_seconds",
        "created_at", "updated_at",
        "app_version", "ruleset_version", "model_version", "schema_version",
    ])

    for c in rows:
        w.writerow([
            c.id, c.scheme_code,
            c.status.value, c.source.value, c.locale,
            c.arm, c.assignment_reason or "", int(bool(c.decision_support_shown)),
            c.rule_result.value if c.rule_result else "",
            json.dumps(c.rule_reasons or [], ensure_ascii=False),
            json.dumps(c.documents or [], ensure_ascii=False),
            c.review_confidence if c.review_confidence is not None else "",
            c.risk_score if c.risk_score is not None else "",
            c.risk_band or "",
            json.dumps(c.top_reasons or [], ensure_ascii=False),
            int(bool(c.audit_flag)),
            c.final_action.value if c.final_action else "",
            c.reason_code.value if c.reason_code else "",
            "" if c.override_flag is None else int(bool(c.override_flag)),
            c.opened_at.isoformat() if c.opened_at else "",
            c.decided_at.isoformat() if c.decided_at else "",
            c.operator_id or "",
            c.sop_version or "",
            c.session_id or "",
            c.meta_duration_seconds or "",
            c.created_at.isoformat() if c.created_at else "",
            c.updated_at.isoformat() if c.updated_at else "",
            c.app_version or "",
            c.ruleset_version or "",
            c.model_version or "",
            c.schema_version or "",
        ])

    record_event(db, models.ActionEnum.EXPORT_CASES, None, {"rows": len(rows), "since": since, "min_risk": min_risk})
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8")


# -------------------------
# GET CASE (enforces blinding)
# -------------------------
@router.get("/{case_id}", response_model=schemas.CaseResponse)
def get_case(case_id: str, db: Session = Depends(get_db)):
    obj = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not obj:
        raise HTTPException(404, "Case not found")

    resp = schemas.CaseResponse.model_validate(obj)

    # Enforce blinding at API boundary
    if obj.arm == "CONTROL":
        resp.review_confidence = None
        resp.risk_score = None
        resp.risk_band = None
        resp.top_reasons = []
        resp.decision_support_shown = False
        resp.audit_flag = None
        resp.override_flag = None

    return resp


# -------------------------
# CREATE CASE (core v1)
# -------------------------
@router.post("/", response_model=schemas.CaseResponse, status_code=201)
def create_case(case: schemas.CaseCreate, response: Response, db: Session = Depends(get_db)):
    response.headers["X-App-Version"] = settings.APP_VERSION

    cfg = get_scheme_config(case.scheme_code)
    if not cfg:
        raise HTTPException(400, "Invalid scheme")

    profile = case.profile.model_dump()
    arm = assign_arm(case.citizen_hash, case.scheme_code)
    record_event(db, models.ActionEnum.ASSIGN_ARM, None, {"arm": arm.name, "reason": arm.reason})

    # ---------- BAU Rules ----------
    rule_out = assistive_decision(case.scheme_code, profile)
    rr_str = rule_out.rule_result.value if hasattr(rule_out.rule_result, "value") else str(rule_out.rule_result)
    rule_reasons = list(rule_out.reasons or [])
    docs = get_document_checklist(case.scheme_code, profile)

    # ---------- ML (computed for all) ----------
    ml_available = True
    ml_failure_id = None

    conf = 0.0
    risk = 1.0
    top_reasons: list[str] = []

    try:
        ai = predict_eligibility(profile) or {}
        conf = float(ai.get("prob", 0.0))
        conf = max(0.0, min(1.0, conf))
        risk = 1.0 - conf
        top_reasons = ai.get("top_reasons", []) or []
        if not isinstance(top_reasons, list):
            top_reasons = []
        top_reasons = [str(x) for x in top_reasons][:5]
    except Exception as e:
        ml_available = False
        ml_failure_id = record_failure(db, "ml_predict", e, {"profile": profile}, "ML_FALLBACK")
        conf = 0.0
        risk = 1.0
        top_reasons = ["ML unavailable"]

    risk_band = _risk_band(risk)

    # Safety gate: route to manual review; never auto-decide
    audit_flag = (not ml_available) or (risk >= 0.7)

    # Status: operationally, high-risk or non-clear rule => in_review
    status = (
        models.StatusEnum.IN_REVIEW
        if rr_str != models.RuleResultEnum.ELIGIBLE_BY_RULE.value or audit_flag
        else models.StatusEnum.NEW
    )

    # Source enum normalization
    src = case.source
    source = models.SourceEnum(src) if src in [s.value for s in models.SourceEnum] else models.SourceEnum.KIOSK_CHAT

    # Persist (store score for BOTH arms; expose only in treatment UI/API)
    new_case = models.Case(
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

        rule_result=models.RuleResultEnum(rr_str),
        rule_reasons=rule_reasons,
        documents=docs,

        review_confidence=conf,
        risk_score=risk,
        risk_band=risk_band,
        top_reasons=top_reasons,
        audit_flag=audit_flag,

        sop_version="SOP_v1",

        app_version=settings.APP_VERSION,
        ruleset_version=cfg.get("ruleset_version") or getattr(settings, "RULESET_VERSION", "dev"),
        model_version=getattr(settings, "MODEL_VERSION", "dev"),
        schema_version=settings.SCHEMA_VERSION,
    )

    try:
        db.add(new_case)
        db.commit()
        db.refresh(new_case)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Duplicate insert")

    record_event(db, models.ActionEnum.CREATE_CASE, new_case.id, {
        "arm": arm.name,
        "decision_support_shown": bool(new_case.decision_support_shown),
        "risk_score": new_case.risk_score,
        "risk_band": new_case.risk_band,
        "audit_flag": bool(new_case.audit_flag),
        "rule_result": rr_str,
        "ml_available": ml_available,
        "ml_failure_id": ml_failure_id,
    })

    resp = schemas.CaseResponse.model_validate(new_case)

    # Enforce blinding at API boundary
    if new_case.arm == "CONTROL":
        resp.review_confidence = None
        resp.risk_score = None
        resp.risk_band = None
        resp.top_reasons = []
        resp.decision_support_shown = False
        resp.audit_flag = None
        resp.override_flag = None

    return resp
