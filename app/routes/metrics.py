# app/routes/metrics.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from statistics import mean

from ..db import get_db
from .. import models
from ..settings import get_settings

router = APIRouter(prefix="/metrics", tags=["metrics"])
settings = get_settings()


@router.get("/")
def metrics_overview(db: Session = Depends(get_db)):
    """
    Pre-registered metrics only.

    1) Difference in means: meta_duration_seconds (T vs C)
    2) Difference in audit_flag rate (logit-ready)
    3) Simple directional bias indicators by scheme / caste / gender
    """
    cases = db.query(models.Case).all()
    if not cases:
        return {"row_count": 0}

    # Split arms
    t = [c for c in cases if c.arm == "TREATMENT"]
    c = [c for c in cases if c.arm == "CONTROL"]

    def safe_mean(xs):
        xs = [x for x in xs if x is not None]
        return mean(xs) if xs else None

    # 1) triage time (difference in means)
    t_time = safe_mean([c.meta_duration_seconds for c in t])
    c_time = safe_mean([c.meta_duration_seconds for c in c])
    triage_diff = None
    if t_time is not None and c_time is not None:
        triage_diff = t_time - c_time

    # 2) audit_flag rate (logit-ready; we just output rates here)
    def rate_audit(xs):
        xs = [int(c.audit_flag) for c in xs]
        return (sum(xs) / len(xs)) if xs else None

    t_audit = rate_audit(t)
    c_audit = rate_audit(c)
    audit_diff = None
    if t_audit is not None and c_audit is not None:
        audit_diff = t_audit - c_audit

    # 3) directional bias indicators (no magnitude over-claim)
    # Example: PMAY, marginalized vs general
    bias_snapshots = []
    pmay_cases = [c for c in cases if c.scheme_code == "PMAY"]
    for group_label, selector in [
        ("caste_marginalized_1", lambda c: c.caste_marginalized == 1),
        ("caste_marginalized_0", lambda c: c.caste_marginalized == 0),
    ]:
        grp = [c for c in pmay_cases if selector(c)]
        bias_snapshots.append({
            "group": group_label,
            "n": len(grp),
            "audit_rate": rate_audit(grp),
        })

    return {
        "row_count": len(cases),
        "triage_time": {
            "treatment_mean": t_time,
            "control_mean": c_time,
            "difference_in_means": triage_diff,
        },
        "audit_flag_rate": {
            "treatment": t_audit,
            "control": c_audit,
            "difference": audit_diff,
        },
        "bias_snapshots": bias_snapshots,
        "notes": [
            "triage_time difference_in_means is the pre-registered estimator for efficiency",
            "audit_flag_rate difference is the pre-registered estimator for intervention intensity",
            "bias_snapshots provide directional signals only; no fairness adjustments are applied here.",
        ],
    }
