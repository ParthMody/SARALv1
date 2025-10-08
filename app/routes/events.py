from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Event

router = APIRouter(prefix="/events", tags=["events"])

@router.get("/recent")
def recent_events(limit: int = 50, db: Session = Depends(get_db)):
    limit = max(1, min(limit, 200))
    rows = (
        db.query(Event)
          .order_by(Event.ts.desc().nullslast())
          .limit(limit)
          .all()
    )
    return [
        {
            "id": str(r.id),
            "case_id": str(r.case_id),
            "action": (r.action.value if hasattr(r.action, "value") else str(r.action)),
            "actor_type": r.actor_type,
            "ts": r.ts,
        }
        for r in rows
    ]
