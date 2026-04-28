# app/routes/dashboard.py
"""
Login and session management routes — SARAL v2 Phase 2.

Landing page collects language only. Demographics are collected at the end
of the session via the survey (item 15: move demographics to end).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    Operator,
    LocaleEnum,
    SessionStatusEnum,
    AuditActionEnum,
)
from app.audit import log_event
from app.settings import get_settings

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")
settings = get_settings()

ADMIN_COOKIE = "saral_admin"


# ─────────────────────────────────────────────
# GET /  →  Landing page (language selection only)
# ─────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse(
        "landing.html",
        {"request": request, "error": None},
    )


# ─────────────────────────────────────────────
# POST /  →  Create operator session (locale only)
# Demographics are collected post-task via survey.
# ─────────────────────────────────────────────

@router.post("/", response_class=HTMLResponse)
def start_session(
    request: Request,
    locale: str = Form("en"),
    db: Session = Depends(get_db),
):
    if locale not in ("en", "mr"):
        locale = "en"

    try:
        locale_enum = LocaleEnum(locale)
    except ValueError:
        locale_enum = LocaleEnum.EN

    # Create operator row — demographics are placeholder until survey
    operator = Operator(
        operator_id      = str(uuid.uuid4()),
        session_id       = str(uuid.uuid4()),
        initials         = "—",          # placeholder, updated at survey
        age              = 0,            # placeholder
        role             = "pending",    # placeholder
        experience_years = 0,            # placeholder
        locale           = locale_enum,
        status           = SessionStatusEnum.IN_PROGRESS,
        cases_assigned   = [],
        cases_completed  = 0,
        session_complete = False,
        language_selected = locale,
        instrument_version = settings.INSTRUMENT_VERSION,
        created_at       = datetime.now(timezone.utc),
    )

    db.add(operator)
    db.commit()
    db.refresh(operator)

    log_event(
        db,
        AuditActionEnum.LOGIN,
        actor_id   = operator.operator_id,
        session_id = operator.session_id,
        payload    = {
            "locale":             locale,
            "instrument_version": settings.INSTRUMENT_VERSION,
            "demographics":       "deferred_to_survey",
        },
    )

    response = RedirectResponse(
        url=f"/session/{operator.session_id}",
        status_code=303,
    )
    response.set_cookie(
        key="session_id",
        value=operator.session_id,
        httponly=True,
        samesite="strict",
        max_age=14400,
    )
    return response


# ─────────────────────────────────────────────
# GET /admin/resume/{session_id}
# Admin-only crash recovery
# ─────────────────────────────────────────────

@router.get("/admin/resume/{session_id}")
def admin_resume_session(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    if request.cookies.get(ADMIN_COOKIE) != settings.ADMIN_SECRET:
        raise HTTPException(403, "Admin access required")

    op = db.query(Operator).filter(Operator.session_id == session_id).first()
    if not op:
        raise HTTPException(404, f"Session {session_id} not found")

    if op.status == SessionStatusEnum.COMPLETED:
        raise HTTPException(409, "Session already completed — cannot resume")

    log_event(
        db,
        AuditActionEnum.LOGIN,
        actor_id   = op.operator_id,
        session_id = session_id,
        payload    = {"action": "admin_resume", "initiated_by": "admin"},
    )

    response = RedirectResponse(
        url=f"/session/{session_id}",
        status_code=303,
    )
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="strict",
        max_age=7200,
    )
    return response


# ─────────────────────────────────────────────
# Reviewer login — demographics collected upfront
# (reviewers don't go through the primary session flow)
# ─────────────────────────────────────────────

@router.get("/reviewer-login", response_class=HTMLResponse)
def reviewer_login_page(request: Request):
    return templates.TemplateResponse(
        "reviewer_login.html",
        {"request": request, "error": None},
    )


@router.post("/reviewer-login", response_class=HTMLResponse)
def reviewer_login(
    request: Request,
    initials:         str = Form(...),
    age:              int = Form(...),
    role:             str = Form(...),
    experience_years: int = Form(...),
    locale:           str = Form("en"),
    db: Session = Depends(get_db),
):
    errors = []
    initials = initials.strip().upper()
    if not initials or len(initials) > 8:
        errors.append("Initials must be 1–8 characters.")
    if not (18 <= age <= 80):
        errors.append("Age must be between 18 and 80.")
    role = role.strip()
    if not role:
        errors.append("Role is required.")
    if not (0 <= experience_years <= 60):
        errors.append("Experience years must be between 0 and 60.")
    if locale not in ("en", "mr"):
        locale = "en"

    if errors:
        return templates.TemplateResponse(
            "reviewer_login.html",
            {"request": request, "error": " ".join(errors)},
            status_code=422,
        )

    try:
        locale_enum = LocaleEnum(locale)
    except ValueError:
        locale_enum = LocaleEnum.EN

    operator = Operator(
        operator_id      = str(uuid.uuid4()),
        session_id       = str(uuid.uuid4()),
        initials         = initials,
        age              = age,
        role             = role,
        experience_years = experience_years,
        locale           = locale_enum,
        status           = SessionStatusEnum.IN_PROGRESS,
        cases_assigned   = [],
        cases_completed  = 0,
        session_complete = False,
        language_selected = locale,
        instrument_version = settings.INSTRUMENT_VERSION,
        created_at       = datetime.now(timezone.utc),
    )

    db.add(operator)
    db.commit()
    db.refresh(operator)

    log_event(
        db,
        AuditActionEnum.LOGIN,
        actor_id   = operator.operator_id,
        session_id = operator.session_id,
        payload    = {
            "role":             role,
            "experience_years": experience_years,
            "locale":           locale,
            "reviewer":         True,
        },
    )

    response = RedirectResponse(
        url=f"/reviewer-waiting/{operator.session_id}",
        status_code=303,
    )
    response.set_cookie(
        key="session_id",
        value=operator.session_id,
        httponly=True,
        samesite="strict",
        max_age=14400,
    )
    return response


@router.get("/reviewer-waiting/{session_id}", response_class=HTMLResponse)
def reviewer_waiting(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    if request.cookies.get("session_id") != session_id:
        return RedirectResponse(url="/reviewer-login", status_code=303)

    op = db.query(Operator).filter(Operator.session_id == session_id).first()
    if not op:
        raise HTTPException(404, "Session not found")

    from app.models import SecondReview
    has_reviews = (
        db.query(SecondReview)
        .filter(SecondReview.secondary_operator_id == op.operator_id)
        .first()
    )
    if has_reviews:
        return RedirectResponse(
            url=f"/review/{session_id}",
            status_code=303,
        )

    return templates.TemplateResponse(
        "reviewer_waiting.html",
        {
            "request":    request,
            "operator":   op,
            "session_id": session_id,
        },
    )