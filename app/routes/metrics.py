from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, case, or_
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from ..settings import get_settings

router = APIRouter(prefix="/metrics", tags=["metrics"])
settings = get_settings()

def _parse_since(since: str | None) -> datetime | None:
    if not since:
        return None
    try:
        return datetime.strptime(since, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid 'since' date. Use YYYY-MM-DD.")

@router.get("/")
def get_metrics(
    since: str | None = Query(None, description="YYYY-MM-DD (optional)"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    since_dt = _parse_since(since)

    base = db.query(models.Case)
    if since_dt:
        base = base.filter(models.Case.created_at >= since_dt)

    total = base.count()

    by_status_rows = (
        base.with_entities(models.Case.status, func.count(models.Case.id))
        .group_by(models.Case.status)
        .all()
    )
    by_status = {str(k): int(v) for k, v in by_status_rows}

    by_scheme_rows = (
        base.with_entities(models.Case.scheme_code, func.count(models.Case.id))
        .group_by(models.Case.scheme_code)
        .all()
    )
    by_scheme = {str(k): int(v) for k, v in by_scheme_rows}

    by_arm_rows = (
        base.with_entities(models.Case.arm, func.count(models.Case.id))
        .group_by(models.Case.arm)
        .all()
    )
    by_arm = {str(k): int(v) for k, v in by_arm_rows}

    def arm_stats(arm_name: str) -> Dict[str, float]:
        row = (
            base.filter(models.Case.arm == arm_name)
            .with_entities(
                func.count(models.Case.id).label("n"),
                func.avg(models.Case.meta_duration_seconds).label("avg_time"),
                func.sum(case((models.Case.audit_flag == True, 1), else_=0)).label("flags"),
            )
            .first()
        )
        n = int(row.n or 0)
        avg_time = float(row.avg_time) if row.avg_time is not None else 0.0
        flags = int(row.flags or 0)
        flag_rate = (flags / n) if n else 0.0
        return {"n": n, "avg_time": avg_time, "flag_rate": flag_rate}

    treatment = arm_stats("TREATMENT")
    control = arm_stats("CONTROL")

    payload: Dict[str, Any] = {
        "by_status": by_status,
        "by_scheme": by_scheme,
        "by_arm": by_arm,
        "meta": {
            "version": settings.APP_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "since_filter": since,
            "total_cases": total,
        },
        "experimental_rct": {
            "treatment": treatment,
            "control": control,
            "delta_analysis": {
                "time_savings_seconds": float(treatment["avg_time"] - control["avg_time"]),
                "audit_rate_diff": float(treatment["flag_rate"] - control["flag_rate"]),
            },
        },
    }

    # Override metrics: only if your schema supports final_action + enum
    has_final_action = hasattr(models.Case, "final_action") and hasattr(models, "FinalActionEnum")
    if has_final_action:
        override = (
            base.filter(models.Case.ai_shown == True)
            .filter(models.Case.flag_reason == "High ML risk score")
            .filter(models.Case.final_action == models.FinalActionEnum.ELIGIBLE_PROVISIONAL)
            .count()
        )
        treatment_total = base.filter(models.Case.ai_shown == True).count()
        payload["override_n"] = int(override)
        payload["treatment_n"] = int(treatment_total)
        payload["override_rate"] = float((override / treatment_total) if treatment_total else 0.0)
    else:
        payload["override_n"] = 0
        payload["treatment_n"] = int(base.filter(models.Case.ai_shown == True).count())
        payload["override_rate"] = 0.0
        payload["override_note"] = "final_action not present in schema; override rate disabled"

    return payload