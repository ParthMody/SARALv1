# app/routes/review.py
"""
Secondary Review Module — SARAL v2 (TDD §9)

Post-hoc only: triggered after all primary sessions are complete.
Triggered for: arm=treatment AND override=True.

Assignment priority (TDD §9.2):
  1. Operator with >= SENIOR_EXPERIENCE_GAP more years than primary → review_type=experienced
  2. Otherwise → random independent operator → review_type=random

Blinding: primary_decision is stored in DB but NEVER returned to the
secondary reviewer. It is revealed only after secondary_decision is submitted.
Enforced at the query layer (TDD §9.3).

Admin-only routes (passcode protected):
  POST /admin/review/assign     → assign all pending second reviews
  GET  /admin/review/status     → see assignment status

Reviewer routes (session-cookie protected):
  GET  /review/{session_id}     → reviewer queue
  POST /review/{session_id}/submit  → submit secondary decision
"""
from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.audit import log_event
from app.db import get_db
from app.models import (
    AuditActionEnum,
    ArmEnum,
    DecisionEnum,
    Evaluation,
    Operator,
    ReviewTypeEnum,
    SecondReview,
    SessionStatusEnum,
    Vignette,
)
from app.settings import get_settings

router    = APIRouter(tags=["review"])
templates = Jinja2Templates(directory="app/templates")
settings  = get_settings()

ADMIN_COOKIE = "saral_admin"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_admin(request: Request) -> bool:
    return request.cookies.get(ADMIN_COOKIE) == settings.ADMIN_SECRET


def _check_session_cookie(request: Request, session_id: str) -> None:
    if request.cookies.get("session_id") != session_id:
        raise HTTPException(403, "Session mismatch.")


# ─────────────────────────────────────────────
# Assignment logic (TDD §9.2)
# ─────────────────────────────────────────────

def _assign_second_reviews(db: Session) -> dict[str, int]:
    """
    Finds all treatment-arm overrides that don't yet have a SecondReview row,
    and assigns a secondary reviewer to each.

    Returns counts: {"assigned": n, "skipped": n}
    """
    # All treatment overrides from completed sessions
    override_evals = (
        db.query(Evaluation, Operator)
        .join(Operator, Operator.session_id == Evaluation.session_id)
        .filter(
            Evaluation.arm      == ArmEnum.TREATMENT,
            Evaluation.override == True,               # noqa: E712
            Operator.status     == SessionStatusEnum.COMPLETED,
        )
        .all()
    )

    # Already-assigned case+primary pairs (avoid duplicates)
    existing = {
        (r.case_id, r.primary_operator_id)
        for r in db.query(SecondReview).all()
    }

    # All completed operators available as secondary reviewers
    all_ops = (
        db.query(Operator)
        .filter(Operator.status == SessionStatusEnum.COMPLETED)
        .all()
    )
    ops_by_id = {op.operator_id: op for op in all_ops}

    assigned = 0
    skipped  = 0
    rng      = random.Random(42)

    for ev, primary_op in override_evals:
        key = (ev.case_id, primary_op.operator_id)
        if key in existing:
            skipped += 1
            continue

        # Candidates: all completed operators except the primary
        candidates = [
            op for op in all_ops
            if op.operator_id != primary_op.operator_id
        ]
        if not candidates:
            skipped += 1
            continue

        # Priority: operator with >= SENIOR_EXPERIENCE_GAP more experience
        senior_candidates = [
            op for op in candidates
            if (op.experience_years - primary_op.experience_years) >= settings.SENIOR_EXPERIENCE_GAP
        ]

        if senior_candidates:
            secondary_op = rng.choice(senior_candidates)
            review_type  = ReviewTypeEnum.EXPERIENCED
        else:
            secondary_op = rng.choice(candidates)
            review_type  = ReviewTypeEnum.RANDOM

        exp_gap = secondary_op.experience_years - primary_op.experience_years

        review = SecondReview(
            case_id               = ev.case_id,
            primary_operator_id   = primary_op.operator_id,
            secondary_operator_id = secondary_op.operator_id,
            experience_gap        = exp_gap,
            review_type           = review_type,
            primary_decision      = ev.decision,   # stored, never served to reviewer
            secondary_decision    = None,
            created_at            = _utcnow(),
        )
        db.add(review)
        existing.add(key)
        assigned += 1

    db.commit()
    return {"assigned": assigned, "skipped": skipped}


# ─────────────────────────────────────────────
# Admin: trigger assignment
# ─────────────────────────────────────────────

@router.post("/admin/review/assign")
def admin_assign_reviews(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        raise HTTPException(403, "Admin access required")

    result = _assign_second_reviews(db)

    log_event(
        db, AuditActionEnum.ADMIN_EXPORT, actor_id="ADMIN",
        payload={"action": "assign_second_reviews", **result},
    )

    return JSONResponse({"ok": True, **result})


@router.get("/admin/review/status")
def admin_review_status(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        raise HTTPException(403, "Admin access required")

    total     = db.query(SecondReview).count()
    pending   = db.query(SecondReview).filter(SecondReview.secondary_decision == None).count()  # noqa: E711
    completed = total - pending

    rows = db.query(SecondReview).order_by(SecondReview.created_at.desc()).all()

    # Build a lookup of operator_id → session_id for reviewer links
    secondary_ids = {r.secondary_operator_id for r in rows if r.secondary_operator_id}
    session_map = {}
    if secondary_ids:
        ops = (
            db.query(Operator)
            .filter(Operator.operator_id.in_(secondary_ids))
            .all()
        )
        session_map = {op.operator_id: op.session_id for op in ops}

    # Group reviews by secondary reviewer so we can show one link per reviewer
    reviewer_sessions: dict[str, str] = {}
    for op_id, sess_id in session_map.items():
        reviewer_sessions[op_id] = sess_id

    data = []
    for r in rows:
        data.append({
            "id":                    r.id,
            "case_id":               r.case_id,
            "primary_operator_id":   r.primary_operator_id,
            "secondary_operator_id": r.secondary_operator_id,
            "secondary_session_id":  session_map.get(r.secondary_operator_id),
            "review_type":           r.review_type.value if r.review_type else None,
            "experience_gap":        r.experience_gap,
            "secondary_decision":    r.secondary_decision.value if r.secondary_decision else None,
            "reviewed_at":           r.reviewed_at.isoformat() if r.reviewed_at else None,
        })

    # Unique reviewers with pending work
    pending_reviewers = {}
    for r in rows:
        if r.secondary_operator_id and r.secondary_decision is None:
            sid = session_map.get(r.secondary_operator_id)
            if sid and r.secondary_operator_id not in pending_reviewers:
                pending_reviewers[r.secondary_operator_id] = sid

    return JSONResponse({
        "total":            total,
        "pending":          pending,
        "completed":        completed,
        "reviews":          data,
        "pending_reviewers": [
            {"operator_id": oid, "session_id": sid}
            for oid, sid in pending_reviewers.items()
        ],
    })


# ─────────────────────────────────────────────
# Reviewer: GET /review/{session_id}
# Shows the secondary reviewer their assigned cases
# PRIMARY DECISION IS NEVER INCLUDED IN THIS VIEW
# ─────────────────────────────────────────────

@router.get("/review/{session_id}", response_class=HTMLResponse)
def reviewer_queue(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _check_session_cookie(request, session_id)

    op = db.query(Operator).filter(Operator.session_id == session_id).first()
    if not op:
        raise HTTPException(404, "Session not found")

    # Cases assigned to this operator as secondary reviewer
    assigned = (
        db.query(SecondReview, Vignette)
        .join(Vignette, Vignette.case_id == SecondReview.case_id)
        .filter(SecondReview.secondary_operator_id == op.operator_id)
        .order_by(SecondReview.created_at)
        .all()
    )

    cases_view: list[dict[str, Any]] = []
    for review, vignette in assigned:
        field_note = (
            vignette.field_note_mr if op.locale.value == "mr"
            else vignette.field_note_en
        )
        full_profile = vignette.profile_data or {}
        visible_profile = {
            k: full_profile[k]
            for k in ["age", "income", "income_period", "rural", "caste_marginalized", "housing_status"]
            if k in full_profile
        }
        for bool_key in ("rural", "caste_marginalized"):
            if bool_key in visible_profile:
                visible_profile[bool_key] = "Yes" if visible_profile[bool_key] else "No"

        cases_view.append({
            "review_id":           review.id,
            "case_id":             vignette.case_id,
            "rule_result":         vignette.rule_result.value,
            "algo_recommendation": vignette.algo_recommendation.value,
            "field_note":          field_note,
            "profile":             visible_profile,
            "secondary_decision":  review.secondary_decision.value if review.secondary_decision else None,
            "submitted":           review.secondary_decision is not None,
            # primary_decision intentionally excluded — blinding enforced here
        })

    completed = sum(1 for c in cases_view if c["submitted"])

    return templates.TemplateResponse(
        "second_review.html",
        {
            "request":    request,
            "operator":   op,
            "cases":      cases_view,
            "completed":  completed,
            "total":      len(cases_view),
            "session_id": session_id,
            "locale":     op.locale.value,
        },
    )


# ─────────────────────────────────────────────
# Reviewer: POST /review/{session_id}/submit
# ─────────────────────────────────────────────

@router.post("/review/{session_id}/submit")
async def reviewer_submit(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _check_session_cookie(request, session_id)

    op = db.query(Operator).filter(Operator.session_id == session_id).first()
    if not op:
        raise HTTPException(404, "Session not found")

    body = await request.json()
    review_id = body.get("review_id")
    decision  = (body.get("decision") or "").strip().lower()
    reasoning = (body.get("reasoning") or "").strip()

    if not review_id:
        raise HTTPException(400, "review_id required")
    if decision not in ("approve", "reject", "escalate"):
        raise HTTPException(400, "decision must be approve / reject / escalate")
    if not reasoning:
        raise HTTPException(400, "reasoning required")

    review = (
        db.query(SecondReview)
        .filter(
            SecondReview.id == review_id,
            SecondReview.secondary_operator_id == op.operator_id,
        )
        .first()
    )
    if not review:
        raise HTTPException(404, "Review not found or not assigned to you")
    if review.secondary_decision is not None:
        raise HTTPException(409, "Already reviewed")

    review.secondary_decision = DecisionEnum(decision)
    review.reviewed_at        = _utcnow()
    db.commit()

    log_event(
        db, AuditActionEnum.CASE_SUBMIT,
        actor_id   = op.operator_id,
        session_id = session_id,
        case_id    = review.case_id,
        payload    = {
            "context":            "second_review",
            "secondary_decision": decision,
            "review_type":        review.review_type.value if review.review_type else None,
        },
    )

    # Reveal primary decision now that secondary is submitted (TDD §9.3)
    return JSONResponse({
        "ok":              True,
        "primary_decision": review.primary_decision.value,
        "agreement":        review.primary_decision.value == decision,
    })


# ─────────────────────────────────────────────
# Admin: open reviewer queue on behalf of reviewer
# Sets the session cookie and redirects to their queue.
# Use this when the admin needs to hand off to a reviewer
# on the same machine, or open it themselves for testing.
# ─────────────────────────────────────────────

@router.get("/admin/review/open/{session_id}")
def admin_open_reviewer_queue(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    if not _is_admin(request):
        raise HTTPException(403, "Admin access required")

    op = db.query(Operator).filter(Operator.session_id == session_id).first()
    if not op:
        raise HTTPException(404, "Session not found")

    # Verify this operator actually has second reviews assigned
    has_reviews = (
        db.query(SecondReview)
        .filter(SecondReview.secondary_operator_id == op.operator_id)
        .first()
    )
    if not has_reviews:
        raise HTTPException(404, "No second reviews assigned to this session")

    response = RedirectResponse(
        url=f"/review/{session_id}",
        status_code=303,
    )
    # Set reviewer's session cookie — overwrites admin's current session cookie
    # on this browser. Admin should use a separate browser/incognito for this.
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="strict",
        max_age=14400,
    )
    return response