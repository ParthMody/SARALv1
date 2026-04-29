# app/routes/review.py
"""
Secondary Review Module — SARAL v2 Phase 2

Design:
  - 10% of ALL primary evaluations sampled uniformly (not override-conditional)
  - Admin manually assigns sampled cases to 3-4 second reviewers
  - Each second reviewer sees same case material as primary (profile, note, recommendation)
  - No primary metadata visible (decision, reasoning, timing, order, override flag)
  - Independent randomisation of case order per reviewer
  - Compare: decision agreement, override agreement, escalation agreement

Workflow:
  1. All primary sessions complete
  2. Admin clicks "Sample for Second Review" → system samples 10% uniformly
  3. Admin selects second reviewers from registered reviewer pool
  4. Admin clicks "Distribute" → cases distributed evenly across selected reviewers
  5. Second reviewers log in, see their queue, complete reviews
"""
from __future__ import annotations

import math
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
SECOND_REVIEW_SAMPLE_RATE = 0.10  # 10% of all primary evaluations


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_admin(request: Request) -> bool:
    return request.cookies.get(ADMIN_COOKIE) == settings.ADMIN_SECRET


def _check_session_cookie(request: Request, session_id: str) -> None:
    if request.cookies.get("session_id") != session_id:
        raise HTTPException(403, "Session mismatch.")


# ─────────────────────────────────────────────
# Step 1: Sample cases for second review
# Admin triggers this after all primary sessions are complete.
# Samples 10% of ALL completed primary evaluations, uniformly.
# ─────────────────────────────────────────────

@router.post("/admin/review/sample")
def admin_sample_for_review(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        raise HTTPException(403, "Admin access required")

    # All submitted evaluations from completed primary sessions
    all_evals = (
        db.query(Evaluation)
        .join(Operator, Operator.session_id == Evaluation.session_id)
        .filter(
            Operator.status == SessionStatusEnum.COMPLETED,
            Operator.session_complete == True,  # noqa: E712
            Evaluation.timestamp_submit.isnot(None),
        )
        .all()
    )

    if not all_evals:
        return JSONResponse({"ok": False, "detail": "No completed evaluations found."})

    # Already sampled case+operator pairs
    existing = {
        (r.case_id, r.primary_operator_id)
        for r in db.query(SecondReview).all()
    }

    # Filter out already-sampled
    eligible = [
        ev for ev in all_evals
        if (ev.case_id, ev.operator_id) not in existing
    ]

    if not eligible:
        return JSONResponse({
            "ok": True,
            "sampled": 0,
            "total_eligible": 0,
            "detail": "All eligible evaluations already sampled.",
        })

    # Sample 10% uniformly
    sample_size = max(1, math.ceil(len(eligible) * SECOND_REVIEW_SAMPLE_RATE))
    rng = random.Random(42)  # fixed seed for reproducibility
    sampled = rng.sample(eligible, min(sample_size, len(eligible)))

    # Create SecondReview rows — unassigned (secondary_operator_id = None)
    created = 0
    for ev in sampled:
        review = SecondReview(
            case_id               = ev.case_id,
            primary_operator_id   = ev.operator_id,
            secondary_operator_id = None,         # unassigned until admin distributes
            experience_gap        = None,
            review_type           = None,
            primary_decision      = ev.decision,  # stored, never served to reviewer
            secondary_decision    = None,
            created_at            = _utcnow(),
        )
        db.add(review)
        created += 1

    db.commit()

    log_event(
        db, AuditActionEnum.ADMIN_EXPORT, actor_id="ADMIN",
        payload={
            "action":          "sample_second_reviews",
            "total_eligible":  len(eligible),
            "sample_size":     sample_size,
            "sampled":         created,
            "sample_rate":     SECOND_REVIEW_SAMPLE_RATE,
        },
    )

    return JSONResponse({
        "ok":              True,
        "total_eligible":  len(eligible),
        "sampled":         created,
        "sample_rate":     SECOND_REVIEW_SAMPLE_RATE,
    })


# ─────────────────────────────────────────────
# Step 2: List available second reviewers
# Returns operators registered via /reviewer-login
# ─────────────────────────────────────────────

@router.get("/admin/review/reviewers")
def admin_list_reviewers(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        raise HTTPException(403, "Admin access required")

    # Reviewers are operators who logged in via /reviewer-login
    # They have cases_assigned = [] (no primary session)
    all_ops = db.query(Operator).all()

    reviewers = []
    for op in all_ops:
        # A reviewer has no cases assigned (never did primary)
        # OR was explicitly created via reviewer-login (cases_assigned is empty)
        is_reviewer = not op.cases_assigned or len(op.cases_assigned) == 0
        if is_reviewer:
            # Count how many reviews already assigned to them
            assigned_count = (
                db.query(SecondReview)
                .filter(SecondReview.secondary_operator_id == op.operator_id)
                .count()
            )
            completed_count = (
                db.query(SecondReview)
                .filter(
                    SecondReview.secondary_operator_id == op.operator_id,
                    SecondReview.secondary_decision.isnot(None),
                )
                .count()
            )
            reviewers.append({
                "operator_id":      op.operator_id,
                "session_id":       op.session_id,
                "initials":         op.initials,
                "role":             op.role,
                "experience_years": op.experience_years,
                "locale":           op.locale.value,
                "assigned":         assigned_count,
                "completed":        completed_count,
            })

    return JSONResponse({"reviewers": reviewers})


# ─────────────────────────────────────────────
# Step 3: Distribute sampled cases to selected reviewers
# Admin selects reviewer IDs, system distributes evenly.
# ─────────────────────────────────────────────

@router.post("/admin/review/distribute")
async def admin_distribute_reviews(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        raise HTTPException(403, "Admin access required")

    body = await request.json()
    reviewer_ids = body.get("reviewer_ids", [])

    if not reviewer_ids or len(reviewer_ids) < 1:
        raise HTTPException(400, "Select at least 1 reviewer")

    # Validate reviewer IDs exist
    reviewers = (
        db.query(Operator)
        .filter(Operator.operator_id.in_(reviewer_ids))
        .all()
    )
    if len(reviewers) != len(reviewer_ids):
        raise HTTPException(400, "One or more reviewer IDs not found")

    reviewer_map = {op.operator_id: op for op in reviewers}

    # Get unassigned sampled reviews
    unassigned = (
        db.query(SecondReview)
        .filter(SecondReview.secondary_operator_id == None)  # noqa: E711
        .order_by(SecondReview.created_at)
        .all()
    )

    if not unassigned:
        return JSONResponse({
            "ok": True,
            "distributed": 0,
            "detail": "No unassigned reviews to distribute.",
        })

    # Filter: reviewer must not have been the primary operator for that case
    rng = random.Random(43)  # different seed from sampling
    rng.shuffle(unassigned)

    assigned_count = 0
    reviewer_idx = 0

    for review in unassigned:
        # Round-robin across reviewers, skipping conflicts
        attempts = 0
        while attempts < len(reviewer_ids):
            candidate_id = reviewer_ids[reviewer_idx % len(reviewer_ids)]
            reviewer_idx += 1

            # Conflict check: reviewer was not the primary operator
            if candidate_id != review.primary_operator_id:
                candidate_op = reviewer_map[candidate_id]
                review.secondary_operator_id = candidate_id
                review.review_type = ReviewTypeEnum.RANDOM

                # Experience gap
                primary_op = db.query(Operator).filter(
                    Operator.operator_id == review.primary_operator_id
                ).first()
                if primary_op:
                    gap = candidate_op.experience_years - primary_op.experience_years
                    review.experience_gap = gap
                    if gap >= settings.SENIOR_EXPERIENCE_GAP:
                        review.review_type = ReviewTypeEnum.EXPERIENCED

                assigned_count += 1
                break

            attempts += 1

    db.commit()

    log_event(
        db, AuditActionEnum.ADMIN_EXPORT, actor_id="ADMIN",
        payload={
            "action":       "distribute_second_reviews",
            "reviewer_ids": reviewer_ids,
            "distributed":  assigned_count,
            "total_pending": len(unassigned),
        },
    )

    return JSONResponse({
        "ok":           True,
        "distributed":  assigned_count,
        "total_pending": len(unassigned),
        "reviewers":    reviewer_ids,
    })


# ─────────────────────────────────────────────
# Admin: review status
# ─────────────────────────────────────────────

@router.get("/admin/review/status")
def admin_review_status(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        raise HTTPException(403, "Admin access required")

    total     = db.query(SecondReview).count()
    unassigned = db.query(SecondReview).filter(
        SecondReview.secondary_operator_id == None  # noqa: E711
    ).count()
    assigned_pending = db.query(SecondReview).filter(
        SecondReview.secondary_operator_id.isnot(None),
        SecondReview.secondary_decision == None,  # noqa: E711
    ).count()
    completed = db.query(SecondReview).filter(
        SecondReview.secondary_decision.isnot(None)
    ).count()

    rows = db.query(SecondReview).order_by(SecondReview.created_at.desc()).all()

    # Session ID lookup for reviewer links
    secondary_ids = {r.secondary_operator_id for r in rows if r.secondary_operator_id}
    session_map = {}
    if secondary_ids:
        ops = db.query(Operator).filter(Operator.operator_id.in_(secondary_ids)).all()
        session_map = {op.operator_id: op.session_id for op in ops}

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
        "unassigned":       unassigned,
        "assigned_pending": assigned_pending,
        "completed":        completed,
        "reviews":          data,
        "pending_reviewers": [
            {"operator_id": oid, "session_id": sid}
            for oid, sid in pending_reviewers.items()
        ],
    })


# ─────────────────────────────────────────────
# Reviewer: GET /review/{session_id}
# Case queue — full isolation from primary metadata
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
        .all()
    )

    if not assigned:
        raise HTTPException(404, "No cases assigned for review")

    # Independent randomisation (item 12) — shuffle by reviewer's operator_id
    rng = random.Random(hash(op.operator_id) % (2**31))
    assigned_list = list(assigned)
    rng.shuffle(assigned_list)

    # Profile keys — no PII (name, survey_no excluded)
    profile_keys = [
        "age", "slum", "claimed_since",
        "voter_roll", "housing", "society", "documents",
    ]

    cases_view: list[dict[str, Any]] = []
    for seq, (review, vignette) in enumerate(assigned_list, start=1):
        field_note = (
            vignette.field_note_mr if op.locale.value == "mr"
            else vignette.field_note_en
        )
        full_profile = vignette.profile_data or {}
        visible_profile = {}
        for k in profile_keys:
            if k in full_profile:
                val = full_profile[k]
                if isinstance(val, list):
                    visible_profile[k] = ", ".join(str(v) for v in val)
                else:
                    visible_profile[k] = val

        cases_view.append({
            "review_id":           review.id,
            "case_id":             vignette.case_id,
            "case_sequence":       seq,   # independent order, not primary's
            "rule_result":         vignette.rule_result.value,
            "algo_recommendation": vignette.algo_recommendation.value,
            "field_note":          field_note,
            "profile":             visible_profile,
            "secondary_decision":  review.secondary_decision.value if review.secondary_decision else None,
            "submitted":           review.secondary_decision is not None,
            # Intentionally excluded: primary_decision, primary reasoning,
            # primary timing, original case order, override flag
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

    review.secondary_decision  = DecisionEnum(decision)
    review.secondary_reasoning = reasoning
    review.reviewed_at         = _utcnow()
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
            "experience_gap":     review.experience_gap,
        },
    )

    # Reveal primary decision after secondary submits
    return JSONResponse({
        "ok":               True,
        "primary_decision": review.primary_decision.value,
        "agreement":        review.primary_decision.value == decision,
    })


# ─────────────────────────────────────────────
# Admin: open reviewer queue (cookie handoff)
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

    has_reviews = (
        db.query(SecondReview)
        .filter(SecondReview.secondary_operator_id == op.operator_id)
        .first()
    )
    if not has_reviews:
        raise HTTPException(404, "No second reviews assigned to this session")

    response = RedirectResponse(url=f"/review/{session_id}", status_code=303)
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="strict",
        max_age=14400,
    )
    return response