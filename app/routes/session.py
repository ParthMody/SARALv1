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
    Balance is enforced at this layer.
    Uses operator_id as seed for reproducibility.
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

    control = draw(ArmEnum.CONTROL, settings.CONTROL_PER_SESSION)
    treatment = draw(ArmEnum.TREATMENT, settings.TREATMENT_PER_SESSION)

    combined = control + treatment
    rng.shuffle(combined)

    db.commit()
    return [v.case_id for v in combined]


# Applicant Profile should contain background covariates, not duplicate the formal SRA record
OPERATOR_VISIBLE_PROFILE_KEYS = [
    "age",
    "income",
    "income_period",
    "caste_marginalized",
]

PROFILE_LABELS = {
    "age": "Age",
    "income": "Income",
    "income_period": "Income Period",
    "caste_marginalized": "Marginalized Caste",
}


def _build_case_view(
    vignette: Vignette,
    evaluation: Evaluation,
    locale: str,
) -> dict[str, Any]:
    """
    Build the dict served to the Jinja2 template / JS openCase().
    - Never exposes arm.
    - Profile filtered to operator-visible background covariates only.
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

    if "caste_marginalized" in visible_profile:
        visible_profile["caste_marginalized"] = (
            "Yes" if visible_profile["caste_marginalized"] else "No"
        )

    return {
        "case_id": vignette.case_id,
        "case_sequence": evaluation.case_sequence,
        "rule_result": vignette.rule_result.value,
        "algo_recommendation": vignette.algo_recommendation.value,
        "field_note": field_note,
        "profile": visible_profile,
        "profile_labels": PROFILE_LABELS,
        "decision": evaluation.decision.value if evaluation.decision else None,
        "reasoning": evaluation.reasoning or "",
        "override": evaluation.override,
        "submitted": evaluation.timestamp_submit is not None,
    }


def _check_session_cookie(request: Request, session_id: str) -> None:
    cookie = _get_session_id_from_cookie(request)
    if cookie != session_id:
        raise HTTPException(403, "Session mismatch. Please log in again.")


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

    if not op.cases_assigned:
        case_ids = _assign_cases(op, db)
        op.cases_assigned = case_ids
        db.commit()
        db.refresh(op)

        for seq, case_id in enumerate(op.cases_assigned, start=1):
            vignette = db.query(Vignette).filter(Vignette.case_id == case_id).first()
            if not vignette:
                continue
            ev = Evaluation(
                operator_id=op.operator_id,
                session_id=op.session_id,
                case_id=case_id,
                arm=vignette.arm,
                algo_recommendation=vignette.algo_recommendation,
                rule_result=vignette.rule_result,
                decision=None,
                case_sequence=seq,
            )
            db.add(ev)
        db.commit()

        log_event(
            db,
            AuditActionEnum.SESSION_START,
            actor_id=op.operator_id,
            session_id=op.session_id,
            payload={
                "cases_assigned": op.cases_assigned,
                "pool_version": settings.POOL_VERSION,
            },
        )

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
        ev = ev_by_case.get(case_id)
        if not vignette or not ev:
            continue
        cases_view.append(_build_case_view(vignette, ev, op.locale.value))

    completed = sum(1 for ev in evaluations if ev.timestamp_submit is not None)
    total_cases = len(op.cases_assigned)

    return templates.TemplateResponse(
        "session.html",
        {
            "request": request,
            "operator": op,
            "cases": cases_view,
            "completed": completed,
            "total_cases": total_cases,
            "session_id": session_id,
            "locale": op.locale.value,
        },
    )


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

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    case_id = (body.get("case_id") or "").strip()
    decision = (body.get("decision") or "").strip().lower()
    reasoning = (body.get("reasoning") or "").strip()
    opened_at_str = body.get("opened_at")

    if not case_id:
        raise HTTPException(400, "case_id is required")
    if decision not in ("approve", "reject", "escalate"):
        raise HTTPException(400, "decision must be approve / reject / escalate")
    if not reasoning:
        raise HTTPException(400, "reasoning is required")

    ev = (
        db.query(Evaluation)
        .filter(
            Evaluation.session_id == session_id,
            Evaluation.case_id == case_id,
        )
        .first()
    )
    if not ev:
        raise HTTPException(404, "Case not assigned to this session")
    if ev.timestamp_submit is not None:
        raise HTTPException(409, "Case already submitted")

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
    ev.timestamp_submit = now
    ev.response_time_sec = (now - ev.timestamp_open).total_seconds()

    ev.decision = DecisionEnum(decision)
    ev.reasoning = reasoning
    ev.override = (ev.decision.value != ev.algo_recommendation.value)

    db.commit()

    op.cases_completed = (
        db.query(Evaluation)
        .filter(
            Evaluation.session_id == session_id,
            Evaluation.timestamp_submit.isnot(None),
        )
        .count()
    )
    db.commit()

    log_event(
        db,
        AuditActionEnum.CASE_SUBMIT,
        actor_id=op.operator_id,
        session_id=session_id,
        case_id=case_id,
        payload={
            "decision": decision,
            "override": ev.override,
            "arm": ev.arm.value,
            "algo_recommendation": ev.algo_recommendation.value,
            "response_time_sec": ev.response_time_sec,
            "case_sequence": ev.case_sequence,
        },
    )

    all_done = op.cases_completed >= settings.CASES_PER_SESSION

    return JSONResponse({
        "ok": True,
        "override": ev.override,
        "all_done": all_done,
    })


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
    salience = body.get("salience_rating")
    standout = body.get("standout_rating")
    confidence = body.get("confidence_rating")

    for name, val in [
        ("salience_rating", salience),
        ("standout_rating", standout),
        ("confidence_rating", confidence),
    ]:
        if val is None or not isinstance(val, int) or not (1 <= val <= 5):
            raise HTTPException(400, f"{name} must be an integer 1–5")

    survey = SurveyResponse(
        operator_id=op.operator_id,
        session_id=session_id,
        salience_rating=salience,
        standout_rating=standout,
        confidence_rating=confidence,
        submitted_at=_utcnow(),
    )
    db.add(survey)

    op.status = SessionStatusEnum.COMPLETED
    op.completed_at = _utcnow()
    db.commit()

    log_event(
        db,
        AuditActionEnum.SURVEY_SUBMIT,
        actor_id=op.operator_id,
        session_id=session_id,
        payload={
            "salience_rating": salience,
            "standout_rating": standout,
            "confidence_rating": confidence,
        },
    )
    log_event(
        db,
        AuditActionEnum.SESSION_END,
        actor_id=op.operator_id,
        session_id=session_id,
        payload={"cases_completed": op.cases_completed},
    )

    return JSONResponse({"ok": True, "redirect": f"/session/{session_id}/complete"})


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