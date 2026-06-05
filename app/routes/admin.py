# app/routes/admin.py
"""
Admin panel for SARAL v2 Phase 2 (Prolific deployment).
  - Session monitor
  - CSV exports with Prolific fields
  - Device logging
  - No second review (agreement computed statistically)
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.audit import log_event
from app.db import get_db
from app.models import (
    AuditActionEnum, Evaluation, Operator,
    SessionStatusEnum, SurveyResponse, Vignette,
)
from app.settings import get_settings

router    = APIRouter(tags=["admin"])
templates = Jinja2Templates(directory="app/templates")
settings  = get_settings()

ADMIN_COOKIE = "saral_admin"


def _is_admin(request: Request) -> bool:
    return request.cookies.get(ADMIN_COOKIE) == settings.ADMIN_SECRET

def _require_admin(request: Request):
    if not _is_admin(request):
        return RedirectResponse(url="/admin", status_code=303)
    return None


# ── Auth ──

@router.get("/admin", response_class=HTMLResponse)
def admin_login_page(request: Request):
    if _is_admin(request):
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    return templates.TemplateResponse("admin_login.html", {"request": request, "error": None})

@router.post("/admin/login", response_class=HTMLResponse)
def admin_login(request: Request, passcode: str = Form(...)):
    if passcode != settings.ADMIN_SECRET:
        return templates.TemplateResponse("admin_login.html", {"request": request, "error": "Incorrect passcode."}, status_code=401)
    resp = RedirectResponse(url="/admin/dashboard", status_code=303)
    resp.set_cookie(key=ADMIN_COOKIE, value=settings.ADMIN_SECRET, httponly=True, samesite="strict", max_age=14400)
    return resp

@router.post("/admin/logout")
def admin_logout():
    resp = RedirectResponse(url="/admin", status_code=303)
    resp.delete_cookie(ADMIN_COOKIE)
    return resp


# ── Dashboard helpers ──

def _session_rows(db: Session) -> list[dict[str, Any]]:
    operators = db.query(Operator).order_by(Operator.created_at.desc()).all()
    rows = []
    for op in operators:
        # Skip if no consent (abandoned at landing)
        if not op.consent_given:
            continue

        avg_rt = (
            db.query(func.avg(Evaluation.response_time_sec))
            .filter(Evaluation.session_id == op.session_id, Evaluation.response_time_sec.isnot(None))
            .scalar()
        )
        overrides = (
            db.query(func.count(Evaluation.id))
            .filter(Evaluation.session_id == op.session_id, Evaluation.override == True)
            .scalar()
        ) or 0

        duration_min = None
        if op.session_start_timestamp and op.session_end_timestamp:
            duration_min = round((op.session_end_timestamp - op.session_start_timestamp).total_seconds() / 60, 1)

        rows.append({
            "prolific_id":     op.prolific_id or "—",
            "session_id":      op.session_id,
            "status":          op.status.value,
            "cases_completed": op.cases_completed,
            "avg_rt_sec":      round(avg_rt, 1) if avg_rt else "—",
            "override_count":  overrides,
            "duration_min":    duration_min or "—",
            "education":       op.highest_education or "—",
            "occupation":      op.occupation_category or "—",
            "experience":      op.public_admin_experience_years if op.public_admin_experience_years is not None else "—",
            "country":         op.country_of_residence or "—",
            "completion_code": op.prolific_completion_code or "—",
            "created_at":      op.created_at.strftime("%Y-%m-%d %H:%M") if op.created_at else "—",
        })
    return rows


def _experiment_stats(db: Session) -> dict[str, Any]:
    total_ops = db.query(func.count(Operator.operator_id)).filter(Operator.consent_given == True).scalar() or 0
    completed = db.query(func.count(Operator.operator_id)).filter(Operator.status == SessionStatusEnum.COMPLETED).scalar() or 0
    in_progress = db.query(func.count(Operator.operator_id)).filter(
        Operator.status == SessionStatusEnum.IN_PROGRESS, Operator.consent_given == True
    ).scalar() or 0
    total_evals = db.query(func.count(Evaluation.id)).filter(Evaluation.timestamp_submit.isnot(None)).scalar() or 0
    overrides = db.query(func.count(Evaluation.id)).filter(Evaluation.override == True).scalar() or 0
    return {
        "total_ops": total_ops, "completed": completed, "in_progress": in_progress,
        "total_evals": total_evals, "overrides": overrides,
        "override_rate": f"{(overrides/total_evals*100):.1f}%" if total_evals else "—",
    }


# ── Dashboard ──

@router.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    redir = _require_admin(request)
    if redir: return redir
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "sessions": _session_rows(db),
        "experiment": _experiment_stats(db),
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    })


# ── Device logging ──

@router.post("/admin/log-device")
async def log_device(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    session_id = body.get("session_id", "")
    op = db.query(Operator).filter(Operator.session_id == session_id).first()
    if not op: return {"ok": False}
    log_event(db, AuditActionEnum.LOGIN, actor_id=op.operator_id, session_id=session_id,
              payload={"action": "device_info", "user_agent": body.get("user_agent", ""),
                       "screen_width": body.get("screen_width"), "screen_height": body.get("screen_height"),
                       "device_type": body.get("device_type", "")})
    return {"ok": True}


# ── CSV Exports ──

@router.get("/admin/export/evaluations.csv")
def export_evaluations(request: Request, db: Session = Depends(get_db)):
    redir = _require_admin(request)
    if redir: return redir

    rows = (
        db.query(Evaluation, Operator, Vignette)
        .join(Operator, Operator.session_id == Evaluation.session_id)
        .join(Vignette, Vignette.case_id == Evaluation.case_id)
        .filter(Evaluation.timestamp_submit.isnot(None))
        .order_by(Evaluation.session_id, Evaluation.case_sequence)
        .all()
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "participant_id", "session_id", "prolific_id",
        "highest_education", "occupation_category", "public_admin_experience_years", "country_of_residence",
        "locale", "instrument_version", "session_complete",
        "case_id", "case_sequence", "profile_id", "category",
        "treatment_flag", "arm", "signal_direction", "algo_recommendation", "rule_result",
        "decision", "override", "reasoning",
        "response_time_sec", "time_to_first_action_ms", "time_after_decision_ms", "is_fast_response",
        "timestamp_open", "timestamp_submit",
        "random_seed", "list_assignment", "case_order_normalized",
        "comprehension_failures", "prolific_completion_code",
    ])

    for ev, op, vig in rows:
        profile = vig.profile_data or {}
        writer.writerow([
            op.operator_id, op.session_id, op.prolific_id or "",
            op.highest_education or "", op.occupation_category or "",
            op.public_admin_experience_years if op.public_admin_experience_years is not None else "",
            op.country_of_residence or "",
            op.locale.value, op.instrument_version or "",
            int(op.session_complete) if op.session_complete is not None else "",
            ev.case_id, ev.case_sequence, vig.pair_id or "",
            profile.get("category", ""),
            1 if ev.arm.value == "treatment" else 0,
            ev.arm.value, profile.get("signal_direction", ""),
            ev.algo_recommendation.value, ev.rule_result.value,
            ev.decision.value if ev.decision else "",
            int(ev.override) if ev.override is not None else "",
            ev.reasoning or "",
            round(ev.response_time_sec, 2) if ev.response_time_sec else "",
            ev.time_to_first_action_ms if ev.time_to_first_action_ms is not None else "",
            ev.time_after_decision_ms if ev.time_after_decision_ms is not None else "",
            int(ev.is_fast_response) if ev.is_fast_response is not None else "",
            ev.timestamp_open.isoformat() if ev.timestamp_open else "",
            ev.timestamp_submit.isoformat() if ev.timestamp_submit else "",
            op.case_order_seed or "",
            op.list_assignment or "",
            round(ev.case_sequence / settings.CASES_PER_SESSION, 3) if ev.case_sequence else "",
            op.comprehension_failures if op.comprehension_failures is not None else "",
            op.prolific_completion_code or "",
        ])

    buf.seek(0)
    return StreamingResponse(buf, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=evaluations.csv"})


@router.get("/admin/export/survey.csv")
def export_survey(request: Request, db: Session = Depends(get_db)):
    redir = _require_admin(request)
    if redir: return redir

    rows = (
        db.query(SurveyResponse, Operator)
        .join(Operator, Operator.operator_id == SurveyResponse.operator_id)
        .order_by(SurveyResponse.submitted_at)
        .all()
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "participant_id", "session_id", "prolific_id",
        "highest_education", "occupation_category", "public_admin_experience_years", "country_of_residence",
        "locale", "instrument_version",
        "salience_rating", "standout_rating", "confidence_rating", "feedback",
        "submitted_at", "session_start_timestamp", "session_end_timestamp",
        "prolific_completion_code",
    ])
    for sr, op in rows:
        writer.writerow([
            op.operator_id, op.session_id, op.prolific_id or "",
            op.highest_education or "", op.occupation_category or "",
            op.public_admin_experience_years if op.public_admin_experience_years is not None else "",
            op.country_of_residence or "",
            op.locale.value, op.instrument_version or "",
            sr.salience_rating, sr.standout_rating, sr.confidence_rating,
            sr.feedback or "",
            sr.submitted_at.isoformat() if sr.submitted_at else "",
            op.session_start_timestamp.isoformat() if op.session_start_timestamp else "",
            op.session_end_timestamp.isoformat() if op.session_end_timestamp else "",
            op.prolific_completion_code or "",
        ])

    buf.seek(0)
    return StreamingResponse(buf, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=survey_responses.csv"})