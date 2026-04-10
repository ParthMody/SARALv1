# app/routes/dashboard.py
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


# ─────────────────────────────────────────────
# GET /  →  Login / landing page
# ─────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse(
        "landing.html",
        {"request": request, "error": None},
    )


# ─────────────────────────────────────────────
# POST /login  →  Create operator + session
# ─────────────────────────────────────────────

@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    initials:         str = Form(...),
    age:              int = Form(...),
    role:             str = Form(...),
    experience_years: int = Form(...),
    locale:           str = Form("en"),
    db: Session = Depends(get_db),
):
    # ── Validation ────────────────────────────
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
            "landing.html",
            {"request": request, "error": " ".join(errors)},
            status_code=422,
        )

    # ── Create operator row ───────────────────
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
        },
    )

    # ── Redirect into session ─────────────────
    # Session route will handle case assignment
    response = RedirectResponse(
        url=f"/session/{operator.session_id}",
        status_code=303,
    )
    # Store session_id in a short-lived cookie for the operator's browser
    response.set_cookie(
        key="session_id",
        value=operator.session_id,
        httponly=True,
        samesite="strict",
        max_age=7200,  # 2 hours — more than enough for a 16-case session
    )
    return response