# app/routes/session.py
"""
Session flow for SARAL v2 Phase 2.
  - List A/B counterbalanced assignment (6 pairs, 12 cases per operator)
  - Dwell time tracking (time_to_first_action, time_after_decision)
  - Fast response flagging (<5s)
  - Randomisation logging (seed + case order)
  - Session timing (start/end timestamps)
"""
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


def _check_session_cookie(request: Request, session_id: str) -> None:
    cookie = _get_session_id_from_cookie(request)
    if cookie != session_id:
        raise HTTPException(403, "Session mismatch. Please log in again.")


# ─────────────────────────────────────────────
# Case assignment — List A/B counterbalance
# ─────────────────────────────────────────────
# Each operator is randomly assigned to List A or B.
# List determines which version (control/treatment) of each pair they see.
# Structured fields are identical within a pair — only the field note differs.

def _assign_cases(operator: Operator, db: Session) -> list[str]:
    """
    Draw 12 from 16 profiles. Within those 12, randomly assign 6 to control
    and 6 to treatment. Pull the matching vignette object for each.

    No List A/B coupling — fully randomised at draw time.
    Seed is logged for reproducibility.
    """
    seed = hash(operator.operator_id) % (2**31)
    rng = random.Random(seed)
    operator.case_order_seed = seed

    # Get all unique profile_ids in the pool
    all_vignettes = db.query(Vignette).all()
    profile_ids = sorted(set(v.pair_id for v in all_vignettes))

    if len(profile_ids) != 16:
        raise HTTPException(
            503,
            f"Expected 16 profiles in pool, found {len(profile_ids)}. Re-seed.",
        )

    # Draw 12 of 16 profile_ids
    drawn_pids = rng.sample(profile_ids, 12)

    # Randomly assign 6 to control, 6 to treatment
    rng.shuffle(drawn_pids)
    control_pids   = set(drawn_pids[:6])
    treatment_pids = set(drawn_pids[6:])

    # Build a lookup: (pair_id, arm) → vignette
    vig_lookup: dict[tuple[int, str], Vignette] = {}
    for v in all_vignettes:
        vig_lookup[(v.pair_id, v.arm.value)] = v

    # Pull the correct vignette for each drawn profile
    drawn_vignettes: list[Vignette] = []
    for pid in drawn_pids:
        arm_str = "control" if pid in control_pids else "treatment"
        key = (pid, arm_str)
        vig = vig_lookup.get(key)
        if not vig:
            raise HTTPException(
                503,
                f"Vignette not found for profile {pid}, arm {arm_str}. Re-seed.",
            )
        drawn_vignettes.append(vig)

    # Shuffle presentation order
    rng.shuffle(drawn_vignettes)

    # Store list assignment as descriptive metadata (which profiles got which arm)
    operator.list_assignment = json.dumps({
        "control_profiles":   sorted(control_pids),
        "treatment_profiles": sorted(treatment_pids),
    })

    # Increment used_count
    for v in drawn_vignettes:
        v.used_count += 1

    db.commit()
    return [v.case_id for v in drawn_vignettes]


# ─────────────────────────────────────────────
# Profile display — SRA Annexure-II aligned
# ─────────────────────────────────────────────

OPERATOR_VISIBLE_PROFILE_KEYS = [
    "electoral_roll_year",
    "structure_type",
    "carpet_area_sqft",
    "pre_cutoff_status",
    "documents",
    "declared_income_band",
    "household_size",
]

PROFILE_LABELS = {
    "electoral_roll_year":   "Electoral Roll Year",
    "structure_type":        "Structure Type",
    "carpet_area_sqft":      "Carpet Area (sq ft)",
    "pre_cutoff_status":     "Pre-Cutoff Status",
    "documents":             "Documents",
    "declared_income_band":  "Declared Income Band",
    "household_size":        "Household Size",
}


def _build_case_view(
    vignette: Vignette,
    evaluation: Evaluation,
    locale: str,
) -> dict[str, Any]:
    """
    Build the dict served to the Jinja2 template / JS openCase().
    Never exposes arm.
    """
    field_note = (
        vignette.field_note_mr if locale == "mr" else vignette.field_note_en
    )
    full_profile = vignette.profile_data or {}

    visible_profile = {}
    for k in OPERATOR_VISIBLE_PROFILE_KEYS:
        if k in full_profile:
            val = full_profile[k]
            # Format lists nicely for display
            if isinstance(val, list):
                visible_profile[k] = ", ".join(str(v) for v in val)
            else:
                visible_profile[k] = val

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


# ─────────────────────────────────────────────
# GET /session/{session_id}
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

    # ── First visit: redirect to practice if not done ─────
    if not op.cases_assigned:
        # Check if comprehension check was completed (logged by POST /session/{id}/comprehension)
        from app.models import AuditLog
        comprehension_done = (
            db.query(AuditLog)
            .filter(
                AuditLog.session_id == session_id,
                AuditLog.action == AuditActionEnum.LOGIN,
                AuditLog.payload.contains("comprehension_check"),
            )
            .first()
        )
        if not comprehension_done:
            return RedirectResponse(url=f"/session/{session_id}/practice", status_code=303)

    # ── First visit: assign cases ─────────────
    if not op.cases_assigned:
        case_ids = _assign_cases(op, db)

        if len(case_ids) != settings.CASES_PER_SESSION:
            raise HTTPException(
                503,
                f"Assignment produced {len(case_ids)} cases, expected "
                f"{settings.CASES_PER_SESSION}. Delete DB and reseed.",
            )

        op.cases_assigned = case_ids

        # Session start timestamp (item 33)
        op.session_start_timestamp = _utcnow()

        # Language logging (item 31)
        op.language_selected = op.locale.value

        # Instrument version (item 10)
        op.instrument_version = settings.INSTRUMENT_VERSION

        db.commit()
        db.refresh(op)

        # Create skeleton Evaluation rows
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

        # Log randomisation (item 9)
        log_event(
            db,
            AuditActionEnum.SESSION_START,
            actor_id   = op.operator_id,
            session_id = op.session_id,
            payload    = {
                "cases_assigned":    op.cases_assigned,
                "list_assignment":   op.list_assignment,
                "case_order_seed":   op.case_order_seed,
                "pool_version":      settings.POOL_VERSION,
                "instrument_version": settings.INSTRUMENT_VERSION,
                "language_selected": op.language_selected,
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

    case_id       = (body.get("case_id") or "").strip()
    decision      = (body.get("decision") or "").strip().lower()
    reasoning     = (body.get("reasoning") or "").strip()
    opened_at_str = body.get("opened_at")

    # Dwell time fields (item 5) — sent from JS
    time_to_first_action_ms = body.get("time_to_first_action_ms")
    time_after_decision_ms  = body.get("time_after_decision_ms")

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

    # Override = 1 when operator disagrees with algo_recommendation
    ev.override = (ev.decision.value != ev.algo_recommendation.value)

    # ── Dwell time (item 5) ──────────────────
    if time_to_first_action_ms is not None:
        try:
            ev.time_to_first_action_ms = int(time_to_first_action_ms)
        except (ValueError, TypeError):
            pass

    if time_after_decision_ms is not None:
        try:
            ev.time_after_decision_ms = int(time_after_decision_ms)
        except (ValueError, TypeError):
            pass

    # ── Fast response flag (item 4) ──────────
    ev.is_fast_response = (
        ev.response_time_sec is not None
        and ev.response_time_sec < settings.FAST_RESPONSE_THRESHOLD_SEC
    )

    db.commit()

    # ── Update operator completion count ──────
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
        actor_id   = op.operator_id,
        session_id = session_id,
        case_id    = case_id,
        payload    = {
            "decision":                 decision,
            "override":                 ev.override,
            "arm":                      ev.arm.value,
            "algo_recommendation":      ev.algo_recommendation.value,
            "response_time_sec":        ev.response_time_sec,
            "case_sequence":            ev.case_sequence,
            "is_fast_response":         ev.is_fast_response,
            "time_to_first_action_ms":  ev.time_to_first_action_ms,
            "time_after_decision_ms":   ev.time_after_decision_ms,
        },
    )

    # ── Check if all cases done ───────────────
    all_done = op.cases_completed >= settings.CASES_PER_SESSION

    return JSONResponse({
        "ok":       True,
        "override": ev.override,
        "all_done": all_done,
    })


# ─────────────────────────────────────────────
# GET /session/{session_id}/survey
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
    salience   = body.get("salience_rating")
    standout   = body.get("standout_rating")
    confidence = body.get("confidence_rating")
    feedback   = (body.get("feedback") or "").strip()

    # Demographics (item 15 — collected post-task)
    initials         = (body.get("initials") or "").strip().upper()
    age_raw          = body.get("age")
    experience_raw   = body.get("experience_years")
    role             = (body.get("role") or "").strip()

    # Validate Likert
    for name, val in [
        ("salience_rating", salience),
        ("standout_rating", standout),
        ("confidence_rating", confidence),
    ]:
        if val is None or not isinstance(val, int) or not (1 <= val <= 5):
            raise HTTPException(400, f"{name} must be an integer 1–5")

    # Validate demographics
    if not initials or len(initials) > 8:
        raise HTTPException(400, "Initials required (1–8 characters)")
    try:
        age = int(age_raw)
        if not (18 <= age <= 80):
            raise ValueError
    except (TypeError, ValueError):
        raise HTTPException(400, "Age must be 18–80")
    try:
        experience_years = int(experience_raw)
        if not (0 <= experience_years <= 60):
            raise ValueError
    except (TypeError, ValueError):
        raise HTTPException(400, "Experience years must be 0–60")
    if not role:
        raise HTTPException(400, "Role is required")

    # ── Update operator demographics ─────────
    op.initials         = initials
    op.age              = age
    op.role             = role
    op.experience_years = experience_years

    survey = SurveyResponse(
        operator_id       = op.operator_id,
        session_id        = session_id,
        salience_rating   = salience,
        standout_rating   = standout,
        confidence_rating = confidence,
        submitted_at      = _utcnow(),
    )
    db.add(survey)

    # Session completion (items 7, 33)
    op.status                 = SessionStatusEnum.COMPLETED
    op.completed_at           = _utcnow()
    op.session_complete       = True
    op.session_end_timestamp  = _utcnow()

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
            "feedback":          feedback,
            "initials":          initials,
            "age":               age,
            "role":              role,
            "experience_years":  experience_years,
        },
    )
    log_event(
        db,
        AuditActionEnum.SESSION_END,
        actor_id   = op.operator_id,
        session_id = session_id,
        payload    = {
            "cases_completed":       op.cases_completed,
            "instrument_version":    op.instrument_version,
            "list_assignment":       op.list_assignment,
        },
    )

    return JSONResponse({"ok": True, "redirect": f"/session/{session_id}/complete"})


# ─────────────────────────────────────────────
# GET /session/{session_id}/complete
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

# ─────────────────────────────────────────────
# GET /session/{session_id}/practice
# Practice case + comprehension check (items 16, 17)
# ─────────────────────────────────────────────

@router.get("/session/{session_id}/practice", response_class=HTMLResponse)
def practice_view(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _check_session_cookie(request, session_id)
    op = _get_operator_or_404(session_id, db)
    return templates.TemplateResponse(
        "practice.html",
        {
            "request":    request,
            "session_id": session_id,
            "locale":     op.locale.value,
        },
    )


# ─────────────────────────────────────────────
# POST /session/{session_id}/comprehension
# Logs whether operator passed comprehension check
# ─────────────────────────────────────────────

@router.post("/session/{session_id}/comprehension")
async def log_comprehension(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _check_session_cookie(request, session_id)
    op = _get_operator_or_404(session_id, db)

    body = await request.json()
    passed   = body.get("passed", False)
    attempts = body.get("attempts", 0)

    log_event(
        db,
        AuditActionEnum.LOGIN,  # reuse LOGIN action type for comprehension
        actor_id   = op.operator_id,
        session_id = session_id,
        payload    = {
            "action":     "comprehension_check",
            "passed":     passed,
            "attempts":   attempts,
        },
    )

    return {"ok": True, "passed": passed, "attempts": attempts}