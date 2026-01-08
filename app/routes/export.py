# app/routes/export.py
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from io import StringIO
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Case

router = APIRouter(prefix="/cases", tags=["export"])


# -------------------------
# Helpers
# -------------------------
def _iso(dt) -> str:
    if not dt:
        return ""
    return dt.isoformat()


def _json_list(val: Any) -> str:
    """
    Preserve structure for research export.
    Always output JSON array/string, never pipe-joined text.
    """
    if val is None:
        return ""
    try:
        return json.dumps(val, ensure_ascii=False)
    except Exception:
        return json.dumps(str(val), ensure_ascii=False)


def _safe_scalar(val: Any) -> Any:
    # Keep CSV sane (avoid "None", keep numbers as numbers)
    if val is None:
        return ""
    return val


def _enum_value(x: Any) -> str:
    if x is None:
        return ""
    return getattr(x, "value", str(x))


def _parse_since(since: str | None) -> datetime | None:
    if not since:
        return None

    # Accept YYYY-MM-DD or ISO8601. Convert naive to UTC-naive for SQLite comparisons.
    try:
        dt = datetime.fromisoformat(since)
    except ValueError:
        try:
            dt = datetime.strptime(since, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "Invalid since. Use YYYY-MM-DD or ISO8601.")

    # If timezone-aware, normalize to UTC and drop tzinfo for DB comparisons if DB stores naive UTC.
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _coerce_enum_filter(model_field, raw: str | None):
    """
    Supports Enum columns and string columns.
    - If raw matches an Enum value, filter on the Enum instance.
    - Else fall back to raw string (for legacy schemas).
    """
    if not raw:
        return None

    enum_cls = getattr(model_field.type, "enum_class", None)
    if enum_cls is not None:
        try:
            return enum_cls(raw)
        except Exception:
            return raw
    return raw


# -------------------------
# Export
# -------------------------
@router.get("/export.csv")
def export_csv(
    db: Session = Depends(get_db),
    scheme: str | None = Query(None),
    status: str | None = Query(None),
    arm: str | None = Query(None),
    since: str | None = Query(None),
    include_control_model_fields: bool = Query(
        False,
        description="If true, export model fields for CONTROL. Default false to enforce blinding.",
    ),
):
    q = db.query(Case)

    if scheme:
        q = q.filter(Case.scheme_code == scheme)

    if status:
        status_val = _coerce_enum_filter(Case.status, status)
        q = q.filter(Case.status == status_val)

    if arm:
        q = q.filter(Case.arm == arm)

    since_dt = _parse_since(since)
    if since_dt:
        q = q.filter(Case.created_at >= since_dt)

    cases = q.order_by(Case.created_at.desc()).all()

    header = [
        # Identity / assignment
        "id",
        "scheme_code",
        "status",
        "source",
        "locale",
        "arm",
        "assignment_reason",
        "decision_support_shown",
        # Verification
        "verification_status",
        "verification_note",
        # Rules
        "rule_result",
        "rule_reasons",
        "documents",
        # ML/AI (blinded in CONTROL unless include_control_model_fields=true)
        "review_confidence",
        "risk_score",
        "risk_band",
        "top_reasons",
        "audit_flag",
        # Human disposition
        "final_action",
        "reason_code",
        "override_flag",
        # Timing
        "created_at",
        "opened_at",
        "decided_at",
        "wait_latency_seconds",      # opened - created
        "triage_latency_seconds",    # decided - opened
        "end_to_end_seconds",        # decided - created
        # Operator + SOP
        "operator_id",
        "sop_version",
        # Meta
        "session_id",
        "meta_duration_seconds",
        "updated_at",
        "app_version",
        "ruleset_version",
        "model_version",
        "schema_version",
    ]

    def iter_csv():
        buf = StringIO()
        writer = csv.writer(buf)

        writer.writerow(header)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)

        for c in cases:
            is_control = (c.arm == "CONTROL")

            # Enforce blinding at export layer (instrument integrity)
            if is_control and not include_control_model_fields:
                review_conf = ""
                risk_score = ""
                risk_band = ""
                top_reasons = "[]"
                audit_flag = ""
                override_flag = ""
                decision_support_shown = False
            else:
                review_conf = _safe_scalar(c.review_confidence)
                risk_score = _safe_scalar(c.risk_score)
                risk_band = _safe_scalar(c.risk_band)
                top_reasons = _json_list(c.top_reasons or [])
                audit_flag = _safe_scalar(c.audit_flag)
                override_flag = "" if c.override_flag is None else int(bool(c.override_flag))
                decision_support_shown = bool(c.decision_support_shown)

            # Latencies
            created_at = c.created_at
            opened_at = c.opened_at
            decided_at = c.decided_at

            wait_latency = ""
            triage_latency = ""
            end_to_end = ""

            if created_at and opened_at:
                wait_latency = (opened_at - created_at).total_seconds()

            if opened_at and decided_at:
                triage_latency = (decided_at - opened_at).total_seconds()

            if created_at and decided_at:
                end_to_end = (decided_at - created_at).total_seconds()

            row = [
                # Identity / assignment
                str(c.id),
                _safe_scalar(c.scheme_code),
                _enum_value(c.status),
                _enum_value(c.source),
                _safe_scalar(c.locale),
                _safe_scalar(c.arm),
                _safe_scalar(c.assignment_reason),
                int(bool(decision_support_shown)),
                # Verification
                _enum_value(getattr(c, "verification_status", None)),
                _safe_scalar(getattr(c, "verification_note", None)),
                # Rules
                _enum_value(c.rule_result),
                _json_list(c.rule_reasons or []),
                _json_list(c.documents or []),
                # ML/AI
                review_conf,
                risk_score,
                risk_band,
                top_reasons,
                audit_flag,
                # Human disposition
                _enum_value(c.final_action),
                _enum_value(c.reason_code),
                override_flag,
                # Timing
                _iso(created_at),
                _iso(opened_at),
                _iso(decided_at),
                wait_latency,
                triage_latency,
                end_to_end,
                # Operator + SOP
                _safe_scalar(getattr(c, "operator_id", None)),
                _safe_scalar(getattr(c, "sop_version", None)),
                # Meta
                _safe_scalar(getattr(c, "session_id", None)),
                _safe_scalar(getattr(c, "meta_duration_seconds", None)),
                _iso(getattr(c, "updated_at", None)),
                _safe_scalar(getattr(c, "app_version", None)),
                _safe_scalar(getattr(c, "ruleset_version", None)),
                _safe_scalar(getattr(c, "model_version", None)),
                _safe_scalar(getattr(c, "schema_version", None)),
            ]

            writer.writerow(row)
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    filename = f"saral_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
