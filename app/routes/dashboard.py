# app/routes/dashboard.py
"""
Session creation and onboarding flow for SARAL v2 Phase 2 (Prolific).

Flow: Landing (Prolific ID + language) → Consent → Demographics → Briefing → ...

No second-reviewer login. No admin resume for reviewers.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    Operator, LocaleEnum, SessionStatusEnum, AuditActionEnum,
)
from app.audit import log_event
from app.settings import get_settings

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")
settings = get_settings()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _check_session_cookie(request: Request, session_id: str) -> None:
    if request.cookies.get("session_id") != session_id:
        raise HTTPException(403, "Session mismatch.")


# ─────────────────────────────────────────────
# GET /  →  Landing page
# ─────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse(
        "landing.html",
        {"request": request, "error": None},
    )


# ─────────────────────────────────────────────
# POST /  →  Create session (Prolific ID + locale)
# ─────────────────────────────────────────────

@router.post("/", response_class=HTMLResponse)
def start_session(
    request: Request,
    locale: str = Form("en"),
    prolific_id: str = Form(""),
    db: Session = Depends(get_db),
):
    if locale not in ("en", "mr"):
        locale = "en"

    prolific_id = prolific_id.strip()

    # Check for duplicate Prolific ID (retain first session only)
    if prolific_id:
        existing = (
            db.query(Operator)
            .filter(Operator.prolific_id == prolific_id)
            .first()
        )
        if existing:
            # Redirect to their existing session
            response = RedirectResponse(
                url=f"/session/{existing.session_id}/consent",
                status_code=303,
            )
            response.set_cookie(
                key="session_id", value=existing.session_id,
                httponly=True, samesite="strict", max_age=14400,
            )
            return response

    operator = Operator(
        operator_id        = str(uuid.uuid4()),
        session_id         = str(uuid.uuid4()),
        prolific_id        = prolific_id or None,
        locale             = LocaleEnum(locale),
        status             = SessionStatusEnum.IN_PROGRESS,
        cases_assigned     = [],
        cases_completed    = 0,
        session_complete   = False,
        language_selected  = locale,
        instrument_version = settings.INSTRUMENT_VERSION,
        created_at         = _utcnow(),
    )

    db.add(operator)
    db.commit()
    db.refresh(operator)

    log_event(
        db, AuditActionEnum.LOGIN,
        actor_id=operator.operator_id,
        session_id=operator.session_id,
        payload={
            "locale": locale,
            "prolific_id": prolific_id or "none",
            "instrument_version": settings.INSTRUMENT_VERSION,
        },
    )

    response = RedirectResponse(
        url=f"/session/{operator.session_id}/consent",
        status_code=303,
    )
    response.set_cookie(
        key="session_id", value=operator.session_id,
        httponly=True, samesite="strict", max_age=14400,
    )
    return response


# ─────────────────────────────────────────────
# GET /session/{session_id}/consent
# ─────────────────────────────────────────────

@router.get("/session/{session_id}/consent", response_class=HTMLResponse)
def consent_page(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _check_session_cookie(request, session_id)
    op = db.query(Operator).filter(Operator.session_id == session_id).first()
    if not op:
        raise HTTPException(404, "Session not found")

    # Already consented? Skip to next step
    if op.consent_given:
        return RedirectResponse(url=f"/session/{session_id}/demographics", status_code=303)

    return templates.TemplateResponse(
        "consent.html",
        {
            "request": request,
            "session_id": session_id,
            "pis_url": settings.PIS_URL,
        },
    )


# ─────────────────────────────────────────────
# POST /session/{session_id}/consent
# ─────────────────────────────────────────────

@router.post("/session/{session_id}/consent")
async def submit_consent(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _check_session_cookie(request, session_id)
    op = db.query(Operator).filter(Operator.session_id == session_id).first()
    if not op:
        raise HTTPException(404, "Session not found")

    body = await request.json()

    op.consent_given     = True
    op.consent_timestamp = _utcnow()
    db.commit()

    log_event(
        db, AuditActionEnum.LOGIN,
        actor_id=op.operator_id,
        session_id=session_id,
        payload={
            "action": "consent",
            "consented": True,
            "consent_timestamp": op.consent_timestamp.isoformat(),
        },
    )

    return JSONResponse({"ok": True})


# ─────────────────────────────────────────────
# GET /session/{session_id}/demographics
# ─────────────────────────────────────────────

@router.get("/session/{session_id}/demographics", response_class=HTMLResponse)
def demographics_page(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _check_session_cookie(request, session_id)
    op = db.query(Operator).filter(Operator.session_id == session_id).first()
    if not op:
        raise HTTPException(404, "Session not found")

    if not op.consent_given:
        return RedirectResponse(url=f"/session/{session_id}/consent", status_code=303)

    # Already filled? Skip to briefing
    if op.highest_education:
        return RedirectResponse(url=f"/session/{session_id}/briefing", status_code=303)

    return templates.TemplateResponse(
        "demographics.html",
        {"request": request, "session_id": session_id},
    )


# ─────────────────────────────────────────────
# POST /session/{session_id}/demographics
# ─────────────────────────────────────────────

@router.post("/session/{session_id}/demographics")
async def submit_demographics(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _check_session_cookie(request, session_id)
    op = db.query(Operator).filter(Operator.session_id == session_id).first()
    if not op:
        raise HTTPException(404, "Session not found")

    body = await request.json()

    op.highest_education             = (body.get("highest_education") or "").strip()
    op.occupation_category           = (body.get("occupation_category") or "").strip()
    op.public_admin_experience_years = int(body.get("public_admin_experience_years", 0))
    op.country_of_residence          = (body.get("country_of_residence") or "").strip()

    if not op.highest_education or not op.occupation_category or not op.country_of_residence:
        raise HTTPException(400, "All demographic fields are required")

    db.commit()

    log_event(
        db, AuditActionEnum.LOGIN,
        actor_id=op.operator_id,
        session_id=session_id,
        payload={
            "action": "demographics",
            "highest_education": op.highest_education,
            "occupation_category": op.occupation_category,
            "public_admin_experience_years": op.public_admin_experience_years,
            "country_of_residence": op.country_of_residence,
        },
    )

    return JSONResponse({"ok": True})