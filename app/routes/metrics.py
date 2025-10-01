# app/routes/metrics.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..db import get_db
from ..models import Case

router = APIRouter(prefix="/metrics", tags=["metrics"])

@router.get("/")
def get_counts(db: Session = Depends(get_db)):
    by_scheme = dict(db.query(Case.scheme_code, func.count()).group_by(Case.scheme_code).all())
    by_status = dict(db.query(Case.status, func.count()).group_by(Case.status).all())
    # cast enum keys to strings for JSON
    by_status = { (k.value if hasattr(k, "value") else k): v for k, v in by_status.items() }
    return {"by_scheme": by_scheme, "by_status": by_status}
