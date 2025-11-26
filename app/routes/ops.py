# app/routes/ops.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Header
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta
from ..db import get_db
from ..models import Case
from ..settings import get_settings
from app.ai.model_loader import MODELS_DIR
import hashlib
import os

router = APIRouter(prefix="/ops", tags=["operations"])
settings = get_settings()

# --- 1. DEPLOYMENT MONITORING (Health) ---
@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """
    Deep Health Check: Verifies DB connection and AI Model presence.
    Used by Cloud Load Balancers (e.g., AWS/Render).
    """
    status = {"api": "online", "version": settings.APP_VERSION, "checks": {}}
    
    # Check DB
    try:
        db.execute(text("SELECT 1"))
        status["checks"]["database"] = "ok"
    except Exception as e:
        status["checks"]["database"] = f"failed: {str(e)}"
        raise HTTPException(503, detail=status)

    # Check AI Models
    elig_path = MODELS_DIR / "eligibility.pkl"
    if elig_path.exists():
        status["checks"]["ai_model"] = "ok"
    else:
        status["checks"]["ai_model"] = "missing"

    return status

# --- 2. MODEL PROVENANCE (Audit) ---
@router.get("/meta/models")
def model_metadata():
    """
    Returns hash of current models to prove which version was used 
    during the experiment (Reproducibility).
    """
    def get_hash(path):
        if not path.exists(): return None
        return hashlib.md5(path.read_bytes()).hexdigest()

    return {
        "eligibility_hash": get_hash(MODELS_DIR / "eligibility.pkl"),
        "intent_hash": get_hash(MODELS_DIR / "intent_nb.pkl"),
        "model_tag": settings.MODEL_VERSION
    }

# --- 3. PRIVACY MODEL (Data Scrubbing) ---
def _prune_pii_task(db: Session):
    """
    Hard Delete of PII profile data for cases older than retention window.
    Keeps the 'id', 'status', 'arm', 'review_confidence' for analysis.
    """
    cutoff = datetime.utcnow() - timedelta(hours=settings.PII_RETENTION_HOURS)
    
    # Since we store profile in the 'Case' object but not as a JSON column in SQLite/Models yet,
    # (Assumption: In v2/Postgres, profile is a JSONB column. In v1, we might just mark them 'archived')
    # For this pilot, let's assume we want to NUKE the free-text intent label if it contains PII.
    
    # Real implementation: Update rows to set sensitive cols to NULL
    # Here we demonstrate the logic structure:
    count = db.query(Case).filter(Case.created_at < cutoff).update(
        {Case.intent_label: "REDACTED", Case.flag_reason: "REDACTED_PII"}, 
        synchronize_session=False
    )
    db.commit()
    print(f"🔒 Privacy Scrub: Redacted {count} old records.")

@router.post("/maintenance/prune")
def trigger_pruning(
    background_tasks: BackgroundTasks, 
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    """
    Triggered by a nightly Cron Job (e.g., GitHub Actions or Render Cron).
    """
    if x_admin_key != settings.MOCK_OTP: # Simple auth for v1
        raise HTTPException(403, "Unauthorized")
    
    background_tasks.add_task(_prune_pii_task, db)
    return {"status": "pruning_initiated"}