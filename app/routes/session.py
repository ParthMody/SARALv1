# app/routes/session.py
from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    AuditActionEnum,
    ArmEnum,
    DecisionEnum,
    Evaluation,
    Operator,
    SessionStatusEnum,
    SurveyResponse,
    Vignette,
)
from app.audit import log_event
from app.settings import get_settings

router = APIRouter(tags=["session"])
templates = Jinja2Templates(directory="app/templates")
settings = get_settings()


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_operator_or_404(session_id: str, db: Session) -> Operator:
    op = db.query(Operator).filter(Operator.session_id == session_id).first()
    if not op:
        raise HTTPException(404, "Session not found")
    return op


def _get_session_id_from_cookie(request: Request) -> str | None:
    return request.cookies.get("session_id")


def _assign_cases(operator: Operator, db: Session) -> list[str]:
    """
    Draw 8 control + 8 treatment vignettes from the pool.
    Balance is enforced at this layer (TDD §5.2).
    Uses operator_id as seed for reproducibility (TDD §13.3).
    Returns an ordered list of case_ids.
    """
    rng = random.Random(operator.operator_id)

    def draw(arm: ArmEnum, n: int) -> list[Vignette]:
        pool = (
            db.query(Vignette)
            .filter(Vignette.arm == arm)
            .order_by(Vignette.used_count.asc())
            .all()
        )
        if len(pool) < n:
            raise HTTPException(
                503,
                f"Vignette pool exhausted for arm={arm.value}. "
                "Re-seed pool before continuing.",
            )
        chosen = rng.sample(pool, n)
        for v in chosen:
            v.used_count += 1
        return chosen

    control   = draw(ArmEnum.CONTROL,   settings.CONTROL_PER_SESSION)
    treatment = draw(ArmEnum.TREATMENT, settings.TREATMENT_PER_SESSION)

    combined = control + treatment
    rng.shuffle(combined)   # re-randomise order across arms (TDD §6.2)

    db.commit()
    return [v.case_id for v in combined]


# Keys exposed to the operator interface (TDD design decision)
OPERATOR_VISIBLE_PROFILE_KEYS = [
    "age", "income", "income_period",
    "rural", "caste_marginalized", "housing_status",
]
PROFILE_LABELS = {
    "age":               "Age",
    "income":            "Monthly Income (Rs.)",
    "income_period":     "Income Period",
    "rural":             "Rural",
    "caste_marginalized": "Marginalized Category",
    "housing_status":    "Housing Status",
}


def _build_case_view(
    vignette: Vignette,
    evaluation: Evaluation,
    locale: str,
) -> dict[str, Any]:
    """
    Build the dict served to the Jinja2 template / JS openCase().
    - Never exposes arm (TDD §6.3).
    - Profile filtered to operator-visible keys only.
    """
    field_note = (
        vignette.field_note_mr if locale == "mr" else vignette.field_note_en
    )
    full_profile = vignette.profile_data or {}

    visible_profile = {
        k: full_profile[k]
        for k in OPERATOR_VISIBLE_PROFILE_KEYS
        if k in full_profile
    }
    for bool_key in ("rural", "caste_marginalized"):
        if bool_key in visible_profile:
            visible_profile[bool_key] = "Yes" if visible_profile[bool_key] else "No"

    return {
        "case_id":             vignette.case_id,
        "case_sequence":       evaluation.case_sequence,
        "rule_result":         vignette.rule_result.value,
        "algo_recommendation": vignette.algo_recommendation.value,
        "field_note":          field_note,
        "profile":             visible_profile,
        "profile_labels":      PROFILE_LABELS,
        "decision":            evaluation.decision.value if evaluation.decision else None,
        "reasoning":           evaluation.reasoning or "",
        "override":            evaluation.override,
        "submitted":           evaluation.timestamp_submit is not None,
    }


def _check_session_cookie(request: Request, session_id: str) -> None:
    """Reject if the cookie doesn't match the URL session_id."""
    cookie = _get_session_id_from_cookie(request)
    if cookie != session_id:
        raise HTTPException(403, "Session mismatch. Please log in again.")


# ─────────────────────────────────────────────
# GET /session/{session_id}
# Initialises case assignment on first visit, then renders queue
# ─────────────────────────────────────────────

@router.get("/session/{session_id}", response_class=HTMLResponse)
def session_view(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _check_session_cookie(request, session_id)
    op = _get_operator_or_404(session_id, db)

    if op.status == SessionStatusEnum.COMPLETED:
        return RedirectResponse(url=f"/session/{session_id}/complete", status_code=303)

    # ── First visit: assign cases ─────────────
    if not op.cases_assigned:
        case_ids = _assign_cases(op, db)
        op.cases_assigned = case_ids
        db.commit()
        db.refresh(op)

        # Create skeleton Evaluation rows (decision=null until submitted)
        for seq, case_id in enumerate(op.cases_assigned, start=1):
            vignette = db.query(Vignette).filter(Vignette.case_id == case_id).first()
            if not vignette:
                continue
            ev = Evaluation(
                operator_id         = op.operator_id,
                session_id          = op.session_id,
                case_id             = case_id,
                arm                 = vignette.arm,
                algo_recommendation = vignette.algo_recommendation,
                rule_result         = vignette.rule_result,
                decision            = None,
                case_sequence       = seq,
            )
            db.add(ev)
        db.commit()

        log_event(
            db,
            AuditActionEnum.SESSION_START,
            actor_id   = op.operator_id,
            session_id = op.session_id,
            payload    = {
                "cases_assigned": op.cases_assigned,
                "pool_version":   settings.POOL_VERSION,
            },
        )

    # ── Build case list for template ──────────
    evaluations = (
        db.query(Evaluation)
        .filter(Evaluation.session_id == session_id)
        .order_by(Evaluation.case_sequence)
        .all()
    )

    ev_by_case = {ev.case_id: ev for ev in evaluations}
    cases_view: list[dict[str, Any]] = []

    for case_id in op.cases_assigned:
        vignette = db.query(Vignette).filter(Vignette.case_id == case_id).first()
        ev       = ev_by_case.get(case_id)
        if not vignette or not ev:
            continue
        cases_view.append(_build_case_view(vignette, ev, op.locale.value))

    completed   = sum(1 for ev in evaluations if ev.timestamp_submit is not None)
    total_cases = len(op.cases_assigned)

    return templates.TemplateResponse(
        "session.html",
        {
            "request":     request,
            "operator":    op,
            "cases":       cases_view,
            "completed":   completed,
            "total_cases": total_cases,
            "session_id":  session_id,
            "locale":      op.locale.value,
        },
    )


# ─────────────────────────────────────────────
# POST /session/{session_id}/evaluate
# Receives a single case decision
# ─────────────────────────────────────────────

@router.post("/session/{session_id}/evaluate")
async def submit_evaluation(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _check_session_cookie(request, session_id)
    op = _get_operator_or_404(session_id, db)

    if op.status == SessionStatusEnum.COMPLETED:
        raise HTTPException(409, "Session already completed")

    # ── Parse body ────────────────────────────
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    case_id   = (body.get("case_id") or "").strip()
    decision  = (body.get("decision") or "").strip().lower()
    reasoning = (body.get("reasoning") or "").strip()
    opened_at_str = body.get("opened_at")

    if not case_id:
        raise HTTPException(400, "case_id is required")
    if decision not in ("approve", "reject", "escalate"):
        raise HTTPException(400, "decision must be approve / reject / escalate")
    if not reasoning:
        raise HTTPException(400, "reasoning is required")

    # ── Fetch evaluation row ──────────────────
    ev = (
        db.query(Evaluation)
        .filter(
            Evaluation.session_id == session_id,
            Evaluation.case_id    == case_id,
        )
        .first()
    )
    if not ev:
        raise HTTPException(404, "Case not assigned to this session")
    if ev.timestamp_submit is not None:
        raise HTTPException(409, "Case already submitted")

    # ── Timestamps ───────────────────────────
    if opened_at_str:
        try:
            ev.timestamp_open = datetime.fromisoformat(
                opened_at_str.replace("Z", "+00:00")
            )
        except ValueError:
            ev.timestamp_open = _utcnow()
    if ev.timestamp_open is None:
        ev.timestamp_open = _utcnow()

    now = _utcnow()
    ev.timestamp_submit   = now
    ev.response_time_sec  = (now - ev.timestamp_open).total_seconds()

    # ── Decision + override ───────────────────
    ev.decision  = DecisionEnum(decision)
    ev.reasoning = reasoning

    # override = 1 when operator disagrees with algo_recommendation (TDD §8.3)
    # rejecting an applicant ≠ overriding the algorithm
    ev.override = (ev.decision.value != ev.algo_recommendation.value)

    db.commit()

    # ── Update operator completion count ──────
    op.cases_completed = (
        db.query(Evaluation)
        .filter(
            Evaluation.session_id   == session_id,
            Evaluation.timestamp_submit.isnot(None),
        )
        .count()
    )
    db.commit()

    log_event(
        db,
        AuditActionEnum.CASE_SUBMIT,
        actor_id   = op.operator_id,
        session_id = session_id,
        case_id    = case_id,
        payload    = {
            "decision":           decision,
            "override":           ev.override,
            "arm":                ev.arm.value,
            "algo_recommendation": ev.algo_recommendation.value,
            "response_time_sec":  ev.response_time_sec,
            "case_sequence":      ev.case_sequence,
        },
    )

    # ── Check if all 16 cases done ────────────
    all_done = op.cases_completed >= settings.CASES_PER_SESSION

    return JSONResponse({
        "ok":       True,
        "override": ev.override,
        "all_done": all_done,
    })


# ─────────────────────────────────────────────
# GET /session/{session_id}/survey
# Post-task salience survey
# ─────────────────────────────────────────────

@router.get("/session/{session_id}/survey", response_class=HTMLResponse)
def survey_view(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _check_session_cookie(request, session_id)
    op = _get_operator_or_404(session_id, db)

    if op.cases_completed < settings.CASES_PER_SESSION:
        raise HTTPException(403, "Complete all cases before the survey")

    existing = (
        db.query(SurveyResponse)
        .filter(SurveyResponse.session_id == session_id)
        .first()
    )
    if existing:
        return RedirectResponse(url=f"/session/{session_id}/complete", status_code=303)

    return templates.TemplateResponse(
        "survey.html",
        {"request": request, "session_id": session_id, "locale": op.locale.value},
    )


# ─────────────────────────────────────────────
# POST /session/{session_id}/survey
# ─────────────────────────────────────────────

@router.post("/session/{session_id}/survey")
async def submit_survey(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _check_session_cookie(request, session_id)
    op = _get_operator_or_404(session_id, db)

    if op.cases_completed < settings.CASES_PER_SESSION:
        raise HTTPException(403, "Complete all cases before the survey")

    existing = (
        db.query(SurveyResponse)
        .filter(SurveyResponse.session_id == session_id)
        .first()
    )
    if existing:
        raise HTTPException(409, "Survey already submitted")

    body = await request.json()
    salience  = body.get("salience_rating")
    standout  = body.get("standout_rating")
    confidence = body.get("confidence_rating")

    for name, val in [
        ("salience_rating", salience),
        ("standout_rating", standout),
        ("confidence_rating", confidence),
    ]:
        if val is None or not isinstance(val, int) or not (1 <= val <= 5):
            raise HTTPException(400, f"{name} must be an integer 1–5")

    survey = SurveyResponse(
        operator_id       = op.operator_id,
        session_id        = session_id,
        salience_rating   = salience,
        standout_rating   = standout,
        confidence_rating = confidence,
        submitted_at      = _utcnow(),
    )
    db.add(survey)

    op.status       = SessionStatusEnum.COMPLETED
    op.completed_at = _utcnow()
    db.commit()

    log_event(
        db,
        AuditActionEnum.SURVEY_SUBMIT,
        actor_id   = op.operator_id,
        session_id = session_id,
        payload    = {
            "salience_rating":   salience,
            "standout_rating":   standout,
            "confidence_rating": confidence,
        },
    )
    log_event(
        db,
        AuditActionEnum.SESSION_END,
        actor_id   = op.operator_id,
        session_id = session_id,
        payload    = {"cases_completed": op.cases_completed},
    )

    return JSONResponse({"ok": True, "redirect": f"/session/{session_id}/complete"})


# ─────────────────────────────────────────────
# GET /session/{session_id}/complete
# Shown after survey — no feedback, no aggregate data
# ─────────────────────────────────────────────

@router.get("/session/{session_id}/complete", response_class=HTMLResponse)
def session_complete(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _check_session_cookie(request, session_id)
    op = _get_operator_or_404(session_id, db)
    return templates.TemplateResponse(
        "complete.html",
        {"request": request, "operator": op},
    )