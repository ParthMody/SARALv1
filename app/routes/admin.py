# app/routes/admin.py
"""
Researcher / admin panel for SARAL v2.
Protected by a hardcoded passcode (ADMIN_SECRET in settings.py).
Accessible at /admin — session-cookie based auth within the browser tab.

Routes:
  GET  /admin              → login form
  POST /admin/login        → validate passcode, set admin cookie
  GET  /admin/dashboard    → session monitor + export buttons
  POST /admin/logout       → clear admin cookie
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
    AuditLog,
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
ADMIN_COOKIE_MAX_AGE = 14400  # 4 hours


# ─────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────

def _is_admin(request: Request) -> bool:
    return request.cookies.get(ADMIN_COOKIE) == settings.ADMIN_SECRET


def _require_admin(request: Request) -> None | RedirectResponse:
    if not _is_admin(request):
        return RedirectResponse(url="/admin", status_code=303)
    return None


# ─────────────────────────────────────────────
# GET /admin  →  login page
# ─────────────────────────────────────────────

@router.get("/admin", response_class=HTMLResponse)
def admin_login_page(request: Request):
    if _is_admin(request):
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    return templates.TemplateResponse(
        "admin_login.html",
        {"request": request, "error": None},
    )


@router.post("/admin/login", response_class=HTMLResponse)
def admin_login(request: Request, passcode: str = Form(...)):
    if passcode != settings.ADMIN_SECRET:
        return templates.TemplateResponse(
            "admin_login.html",
            {"request": request, "error": "Incorrect passcode."},
            status_code=401,
        )
    resp = RedirectResponse(url="/admin/dashboard", status_code=303)
    resp.set_cookie(
        key=ADMIN_COOKIE,
        value=settings.ADMIN_SECRET,
        httponly=True,
        samesite="strict",
        max_age=ADMIN_COOKIE_MAX_AGE,
    )
    return resp


@router.post("/admin/logout")
def admin_logout():
    resp = RedirectResponse(url="/admin", status_code=303)
    resp.delete_cookie(ADMIN_COOKIE)
    return resp


# ─────────────────────────────────────────────
# Helpers for dashboard stats
# ─────────────────────────────────────────────

def _session_rows(db: Session) -> list[dict[str, Any]]:
    operators = db.query(Operator).order_by(Operator.created_at.desc()).all()
    rows = []
    for op in operators:
        # Average response time for this operator
        avg_rt = (
            db.query(func.avg(Evaluation.response_time_sec))
            .filter(
                Evaluation.session_id == op.session_id,
                Evaluation.response_time_sec.isnot(None),
            )
            .scalar()
        )
        # Override count
        overrides = (
            db.query(func.count(Evaluation.id))
            .filter(
                Evaluation.session_id == op.session_id,
                Evaluation.override == True,  # noqa: E712
            )
            .scalar()
        ) or 0

        duration_min = None
        if op.created_at and op.completed_at:
            duration_min = round(
                (op.completed_at - op.created_at).total_seconds() / 60, 1
            )

        rows.append({
            "operator_id":      op.operator_id,
            "session_id":       op.session_id,
            "initials":         op.initials,
            "role":             op.role,
            "experience_years": op.experience_years,
            "locale":           op.locale.value,
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
        Operator.status == SessionStatusEnum.COMPLETED
    ).scalar() or 0
    in_progress = db.query(func.count(Operator.operator_id)).filter(
        Operator.status == SessionStatusEnum.IN_PROGRESS
    ).scalar() or 0
    total_evals = db.query(func.count(Evaluation.id)).filter(
        Evaluation.timestamp_submit.isnot(None)
    ).scalar() or 0
    overrides   = db.query(func.count(Evaluation.id)).filter(
        Evaluation.override == True  # noqa: E712
    ).scalar() or 0
    return {
        "total_ops":    total_ops,
        "completed":    completed,
        "in_progress":  in_progress,
        "total_evals":  total_evals,
        "overrides":    overrides,
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

    log_event(db, AuditActionEnum.ADMIN_EXPORT, actor_id="ADMIN",
              payload={"action": "viewed_dashboard"})

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
# GET /admin/export/evaluations.csv
# ─────────────────────────────────────────────

@router.get("/admin/export/evaluations.csv")
def export_evaluations(request: Request, db: Session = Depends(get_db)):
    redir = _require_admin(request)
    if redir:
        return redir

    rows = (
        db.query(Evaluation, Operator)
        .join(Operator, Operator.session_id == Evaluation.session_id)
        .filter(Evaluation.timestamp_submit.isnot(None))
        .order_by(Evaluation.session_id, Evaluation.case_sequence)
        .all()
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "operator_id", "session_id", "initials", "role", "experience_years",
        "locale", "case_id", "case_sequence", "arm", "algo_recommendation",
        "rule_result", "decision", "override", "response_time_sec",
        "timestamp_open", "timestamp_submit", "reasoning",
    ])
    for ev, op in rows:
        writer.writerow([
            op.operator_id, op.session_id, op.initials, op.role,
            op.experience_years, op.locale.value,
            ev.case_id, ev.case_sequence,
            ev.arm.value, ev.algo_recommendation.value, ev.rule_result.value,
            ev.decision.value if ev.decision else "",
            int(ev.override) if ev.override is not None else "",
            round(ev.response_time_sec, 2) if ev.response_time_sec else "",
            ev.timestamp_open.isoformat() if ev.timestamp_open else "",
            ev.timestamp_submit.isoformat() if ev.timestamp_submit else "",
            ev.reasoning or "",
        ])

    log_event(db, AuditActionEnum.ADMIN_EXPORT, actor_id="ADMIN",
              payload={"export": "evaluations", "rows": len(rows)})

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=evaluations.csv"},
    )


# ─────────────────────────────────────────────
# GET /admin/export/survey.csv
# ─────────────────────────────────────────────

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
        "locale", "salience_rating", "standout_rating", "confidence_rating",
        "submitted_at",
    ])
    for sr, op in rows:
        writer.writerow([
            op.operator_id, op.session_id, op.initials, op.role,
            op.experience_years, op.locale.value,
            sr.salience_rating, sr.standout_rating, sr.confidence_rating,
            sr.submitted_at.isoformat() if sr.submitted_at else "",
        ])

    log_event(db, AuditActionEnum.ADMIN_EXPORT, actor_id="ADMIN",
              payload={"export": "survey", "rows": len(rows)})

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=survey_responses.csv"},
    )


# ─────────────────────────────────────────────
# GET /admin/export/second_reviews.csv
# ─────────────────────────────────────────────

@router.get("/admin/export/second_reviews.csv")
def export_second_reviews(request: Request, db: Session = Depends(get_db)):
    redir = _require_admin(request)
    if redir:
        return redir

    rows = db.query(SecondReview).order_by(SecondReview.created_at).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "case_id", "primary_operator_id", "secondary_operator_id",
        "experience_gap", "review_type",
        "primary_decision", "secondary_decision",
        "created_at", "reviewed_at",
    ])
    for r in rows:
        writer.writerow([
            r.id, r.case_id, r.primary_operator_id, r.secondary_operator_id or "",
            r.experience_gap or "", r.review_type.value if r.review_type else "",
            r.primary_decision.value if r.primary_decision else "",
            r.secondary_decision.value if r.secondary_decision else "",
            r.created_at.isoformat() if r.created_at else "",
            r.reviewed_at.isoformat() if r.reviewed_at else "",
        ])

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=second_reviews.csv"},
    )