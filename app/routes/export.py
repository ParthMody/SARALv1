from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_
from ..db import get_db
from ..models import Case
from datetime import datetime
import csv, io

router = APIRouter(prefix="/cases", tags=["export"])

def _parse_dt(s: str | None):
    if not s: return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        try:
            return datetime.strptime(s, "%Y-%m-%d")
        except Exception:
            return None

@router.get("/export.csv")
def export_csv(
    db: Session = Depends(get_db),
    scheme: str | None = None,
    status: str | None = None,
    flags: bool = Query(False, description="Only audit-flagged"),
    min_conf: float | None = None,
    since: str | None = None,
):
    q = db.query(Case)
    if scheme: q = q.filter(Case.scheme_code == scheme)
    if status: q = q.filter(Case.status == status)
    if flags:  q = q.filter(Case.audit_flag == True)
    if min_conf is not None: q = q.filter(Case.review_confidence >= float(min_conf))
    dt = _parse_dt(since)
    if dt: q = q.filter(Case.created_at >= dt)

    rows = q.order_by(Case.created_at.desc().nullslast()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id","scheme_code","status","locale",
        "review_confidence","audit_flag","flag_reason","intent_label",
        "created_at","updated_at"
    ])
    for c in rows:
        writer.writerow([
            c.id, c.scheme_code, c.status, c.locale,
            c.review_confidence, c.audit_flag, c.flag_reason, c.intent_label,
            c.created_at, c.updated_at
        ])
    output.seek(0)
    return StreamingResponse(
        output, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cases_export.csv"}
    )
