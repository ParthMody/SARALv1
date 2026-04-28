# app/routes/admin.py
"""
Admin panel for SARAL v2 Phase 2.
  - Session monitor with resume
  - CSV exports with full column set (dwell time, fast response, signal direction, etc.)
  - Device logging endpoint
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
    AuditActionEnum,
    Evaluation,
    Operator,
    SecondReview,
    SessionStatusEnum,
    SurveyResponse,
    Vignette,
)
from app.settings import get_settings

router    = APIRouter(tags=["admin"])
templates = Jinja2Templates(directory="app/templates")
settings  = get_settings()

ADMIN_COOKIE = "saral_admin"
ADMIN_COOKIE_MAX_AGE = 14400


# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────

def _is_admin(request: Request) -> bool:
    return request.cookies.get(ADMIN_COOKIE) == settings.ADMIN_SECRET

def _require_admin(request: Request):
    if not _is_admin(request):
        return RedirectResponse(url="/admin", status_code=303)
    return None


# ─────────────────────────────────────────────
# Login / Logout
# ─────────────────────────────────────────────

@router.get("/admin", response_class=HTMLResponse)
def admin_login_page(request: Request):
    if _is_admin(request):
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    return templates.TemplateResponse("admin_login.html", {"request": request, "error": None})

@router.post("/admin/login", response_class=HTMLResponse)
def admin_login(request: Request, passcode: str = Form(...)):
    if passcode != settings.ADMIN_SECRET:
        return templates.TemplateResponse(
            "admin_login.html", {"request": request, "error": "Incorrect passcode."}, status_code=401)
    resp = RedirectResponse(url="/admin/dashboard", status_code=303)
    resp.set_cookie(key=ADMIN_COOKIE, value=settings.ADMIN_SECRET,
                    httponly=True, samesite="strict", max_age=ADMIN_COOKIE_MAX_AGE)
    return resp

@router.post("/admin/logout")
def admin_logout():
    resp = RedirectResponse(url="/admin", status_code=303)
    resp.delete_cookie(ADMIN_COOKIE)
    return resp


# ─────────────────────────────────────────────
# Dashboard helpers
# ─────────────────────────────────────────────

def _session_rows(db: Session) -> list[dict[str, Any]]:
    """Only show primary operators (those with cases assigned), not reviewers."""
    operators = db.query(Operator).order_by(Operator.created_at.desc()).all()
    rows = []
    for op in operators:
        # Skip reviewers (no cases assigned = reviewer)
        if not op.cases_assigned or len(op.cases_assigned) == 0:
            continue
        avg_rt = (
            db.query(func.avg(Evaluation.response_time_sec))
            .filter(Evaluation.session_id == op.session_id,
                    Evaluation.response_time_sec.isnot(None))
            .scalar()
        )
        overrides = (
            db.query(func.count(Evaluation.id))
            .filter(Evaluation.session_id == op.session_id,
                    Evaluation.override == True)  # noqa: E712
            .scalar()
        ) or 0

        duration_min = None
        if op.session_start_timestamp and op.session_end_timestamp:
            duration_min = round(
                (op.session_end_timestamp - op.session_start_timestamp).total_seconds() / 60, 1)
        elif op.created_at and op.completed_at:
            duration_min = round(
                (op.completed_at - op.created_at).total_seconds() / 60, 1)

        # Parse list_assignment (now JSON or None)
        list_info = "—"
        if op.list_assignment:
            try:
                la = json.loads(op.list_assignment)
                c_count = len(la.get("control_profiles", []))
                t_count = len(la.get("treatment_profiles", []))
                list_info = f"C:{c_count} T:{t_count}"
            except (json.JSONDecodeError, TypeError):
                list_info = str(op.list_assignment)[:12]

        rows.append({
            "operator_id":      op.operator_id,
            "session_id":       op.session_id,
            "initials":         op.initials,
            "role":             op.role,
            "experience_years": op.experience_years,
            "locale":           op.locale.value,
            "list_assignment":  list_info,
            "status":           op.status.value,
            "cases_completed":  op.cases_completed,
            "avg_rt_sec":       round(avg_rt, 1) if avg_rt else "—",
            "override_count":   overrides,
            "duration_min":     duration_min or "—",
            "created_at":       op.created_at.strftime("%Y-%m-%d %H:%M") if op.created_at else "—",
        })
    return rows


def _pool_stats(db: Session) -> dict[str, Any]:
    total    = db.query(func.count(Vignette.case_id)).scalar() or 0
    used_any = db.query(func.count(Vignette.case_id)).filter(Vignette.used_count > 0).scalar() or 0
    return {"total": total, "used_any": used_any}


def _experiment_stats(db: Session) -> dict[str, Any]:
    total_ops   = db.query(func.count(Operator.operator_id)).scalar() or 0
    completed   = db.query(func.count(Operator.operator_id)).filter(
        Operator.status == SessionStatusEnum.COMPLETED).scalar() or 0
    in_progress = db.query(func.count(Operator.operator_id)).filter(
        Operator.status == SessionStatusEnum.IN_PROGRESS).scalar() or 0
    total_evals = db.query(func.count(Evaluation.id)).filter(
        Evaluation.timestamp_submit.isnot(None)).scalar() or 0
    overrides   = db.query(func.count(Evaluation.id)).filter(
        Evaluation.override == True).scalar() or 0  # noqa: E712
    return {
        "total_ops":     total_ops,
        "completed":     completed,
        "in_progress":   in_progress,
        "total_evals":   total_evals,
        "overrides":     overrides,
        "override_rate": f"{(overrides/total_evals*100):.1f}%" if total_evals else "—",
    }


# ─────────────────────────────────────────────
# GET /admin/dashboard
# ─────────────────────────────────────────────

@router.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    redir = _require_admin(request)
    if redir:
        return redir

    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request":    request,
            "sessions":   _session_rows(db),
            "pool":       _pool_stats(db),
            "experiment": _experiment_stats(db),
            "generated":  datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        },
    )


# ─────────────────────────────────────────────
# GET /admin/resume/{session_id} — crash recovery
# ─────────────────────────────────────────────

@router.get("/admin/resume/{session_id}")
def admin_resume_session(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    if not _is_admin(request):
        return RedirectResponse(url="/admin", status_code=303)

    op = db.query(Operator).filter(Operator.session_id == session_id).first()
    if not op:
        return RedirectResponse(url="/admin/dashboard", status_code=303)

    if op.status == SessionStatusEnum.COMPLETED:
        return RedirectResponse(url="/admin/dashboard", status_code=303)

    log_event(db, AuditActionEnum.LOGIN, actor_id=op.operator_id,
              session_id=session_id,
              payload={"action": "admin_resume", "initiated_by": "admin"})

    response = RedirectResponse(url=f"/session/{session_id}", status_code=303)
    response.set_cookie(key="session_id", value=session_id,
                        httponly=True, samesite="strict", max_age=7200)
    return response


# ─────────────────────────────────────────────
# POST /admin/log-device — device logging (item 32)
# Called by JS on session start
# ─────────────────────────────────────────────

@router.post("/admin/log-device")
async def log_device(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    session_id = body.get("session_id", "")
    op = db.query(Operator).filter(Operator.session_id == session_id).first()
    if not op:
        return {"ok": False}

    log_event(db, AuditActionEnum.LOGIN, actor_id=op.operator_id,
              session_id=session_id,
              payload={
                  "action":       "device_info",
                  "user_agent":   body.get("user_agent", ""),
                  "screen_width": body.get("screen_width"),
                  "screen_height": body.get("screen_height"),
                  "device_type":  body.get("device_type", ""),
              })
    return {"ok": True}


# ─────────────────────────────────────────────
# CSV EXPORTS — full column set
# ─────────────────────────────────────────────

@router.get("/admin/export/evaluations.csv")
def export_evaluations(request: Request, db: Session = Depends(get_db)):
    redir = _require_admin(request)
    if redir:
        return redir

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
        # ── Operator
        "operator_id", "session_id", "initials", "role", "experience_years",
        # ── Session metadata
        "locale", "language_selected", "instrument_version",
        "session_complete", "device_type",
        # ── Case identification
        "case_id", "case_sequence", "profile_id", "category",
        # ── Experimental (critical)
        "treatment_flag", "arm", "signal_direction",
        "algo_recommendation", "rule_result",
        # ── Decision
        "decision", "override", "reasoning",
        # ── Timing (high value)
        "response_time_sec",
        "time_to_first_action_ms", "time_after_decision_ms",
        "is_fast_response",
        "timestamp_open", "timestamp_submit",
        # ── Randomisation (reproducibility)
        "random_seed", "list_assignment",
        # ── Fatigue / learning
        "case_order_normalized",
        # ── Flag
        "is_second_review",
    ])

    for ev, op, vig in rows:
        profile = vig.profile_data or {}
        writer.writerow([
            # Operator
            op.operator_id, op.session_id, op.initials, op.role,
            op.experience_years,
            # Session metadata
            op.locale.value,
            op.language_selected or op.locale.value,
            op.instrument_version or "",
            int(op.session_complete) if op.session_complete is not None else "",
            "laptop",  # default for primary sessions (supervised on researcher laptop)
            # Case identification
            ev.case_id, ev.case_sequence,
            vig.pair_id or "",
            profile.get("category", ""),
            # Experimental
            1 if ev.arm.value == "treatment" else 0,  # treatment_flag
            ev.arm.value,
            profile.get("signal_direction", ""),
            ev.algo_recommendation.value, ev.rule_result.value,
            # Decision
            ev.decision.value if ev.decision else "",
            int(ev.override) if ev.override is not None else "",
            ev.reasoning or "",
            # Timing
            round(ev.response_time_sec, 2) if ev.response_time_sec else "",
            ev.time_to_first_action_ms if ev.time_to_first_action_ms is not None else "",
            ev.time_after_decision_ms if ev.time_after_decision_ms is not None else "",
            int(ev.is_fast_response) if ev.is_fast_response is not None else "",
            ev.timestamp_open.isoformat() if ev.timestamp_open else "",
            ev.timestamp_submit.isoformat() if ev.timestamp_submit else "",
            # Randomisation
            op.case_order_seed or "",
            op.list_assignment or "",
            # Fatigue / learning control
            round(ev.case_sequence / settings.CASES_PER_SESSION, 3) if ev.case_sequence else "",
            # Flag
            0,  # is_second_review = 0 for primary evaluations
        ])

    log_event(db, AuditActionEnum.ADMIN_EXPORT, actor_id="ADMIN",
              payload={"export": "evaluations", "rows": len(rows)})

    buf.seek(0)
    return StreamingResponse(buf, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=evaluations.csv"})


@router.get("/admin/export/survey.csv")
def export_survey(request: Request, db: Session = Depends(get_db)):
    redir = _require_admin(request)
    if redir:
        return redir

    rows = (
        db.query(SurveyResponse, Operator)
        .join(Operator, Operator.operator_id == SurveyResponse.operator_id)
        .order_by(SurveyResponse.submitted_at)
        .all()
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "operator_id", "session_id", "initials", "role", "experience_years",
        "locale", "list_assignment", "instrument_version",
        "salience_rating", "standout_rating", "confidence_rating",
        "feedback", "submitted_at",
        "session_start_timestamp", "session_end_timestamp",
    ])
    for sr, op in rows:
        writer.writerow([
            op.operator_id, op.session_id, op.initials, op.role,
            op.experience_years, op.locale.value,
            op.list_assignment or "", op.instrument_version or "",
            sr.salience_rating, sr.standout_rating, sr.confidence_rating,
            sr.feedback or "",
            sr.submitted_at.isoformat() if sr.submitted_at else "",
            op.session_start_timestamp.isoformat() if op.session_start_timestamp else "",
            op.session_end_timestamp.isoformat() if op.session_end_timestamp else "",
        ])

    log_event(db, AuditActionEnum.ADMIN_EXPORT, actor_id="ADMIN",
              payload={"export": "survey", "rows": len(rows)})

    buf.seek(0)
    return StreamingResponse(buf, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=survey_responses.csv"})


@router.get("/admin/export/second_reviews.csv")
def export_second_reviews(request: Request, db: Session = Depends(get_db)):
    redir = _require_admin(request)
    if redir:
        return redir

    rows = db.query(SecondReview).order_by(SecondReview.created_at).all()

    # Pre-fetch all operators for initials lookup
    all_ops = {op.operator_id: op for op in db.query(Operator).all()}

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        # ── Review identification
        "review_id", "case_id", "profile_id", "category", "signal_direction",
        # ── Experimental
        "treatment_flag", "arm", "algo_recommendation", "rule_result",
        # ── Primary reviewer
        "primary_operator_id", "primary_initials", "primary_decision",
        # ── Secondary reviewer
        "second_reviewer_id", "secondary_initials", "secondary_decision",
        "secondary_reasoning",
        "experience_gap", "review_type",
        # ── Agreement
        "agreement",
        # ── Timing
        "created_at", "reviewed_at", "review_time_sec",
        # ── Flag
        "is_second_review",
    ])

    for r in rows:
        vig = db.query(Vignette).filter(Vignette.case_id == r.case_id).first()
        profile = vig.profile_data if vig else {}

        # Operator initials
        primary_op = all_ops.get(r.primary_operator_id)
        secondary_op = all_ops.get(r.secondary_operator_id) if r.secondary_operator_id else None

        # Agreement
        agreement = ""
        if r.primary_decision and r.secondary_decision:
            agreement = 1 if r.primary_decision.value == r.secondary_decision.value else 0

        # Review time (seconds between created_at and reviewed_at)
        review_time = ""
        if r.created_at and r.reviewed_at:
            review_time = round((r.reviewed_at - r.created_at).total_seconds(), 2)

        writer.writerow([
            # Review identification
            r.id, r.case_id,
            vig.pair_id if vig else "",
            profile.get("category", ""),
            profile.get("signal_direction", ""),
            # Experimental
            1 if vig and vig.arm.value == "treatment" else 0,
            vig.arm.value if vig else "",
            vig.algo_recommendation.value if vig else "",
            vig.rule_result.value if vig else "",
            # Primary
            r.primary_operator_id,
            primary_op.initials if primary_op else "",
            r.primary_decision.value if r.primary_decision else "",
            # Secondary
            r.secondary_operator_id or "",
            secondary_op.initials if secondary_op else "",
            r.secondary_decision.value if r.secondary_decision else "",
            r.secondary_reasoning or "",
            r.experience_gap if r.experience_gap is not None else "",
            r.review_type.value if r.review_type else "",
            # Agreement
            agreement,
            # Timing
            r.created_at.isoformat() if r.created_at else "",
            r.reviewed_at.isoformat() if r.reviewed_at else "",
            review_time,
            # Flag
            1,
        ])

    buf.seek(0)
    return StreamingResponse(buf, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=second_reviews.csv"})