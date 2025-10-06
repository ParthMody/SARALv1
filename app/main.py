# app/main.py
from fastapi import FastAPI
from .db import Base, engine, SessionLocal
from . import models
from .routes import cases, metrics, dashboard, events
from .logging_config import log_event

app = FastAPI(title="SARAL v1 API")

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.query(models.Scheme).first():
            db.add_all([
                models.Scheme(code="UJJ", name="PM Ujjwala Yojana"),
                models.Scheme(code="PMAY", name="PM Awas Yojana"),
            ])
            db.commit()
    finally:
        db.close()

# Register routes
app.include_router(cases.router)
app.include_router(metrics.router)
app.include_router(dashboard.router)
app.include_router(events.router)

@app.get("/")
def health():
    log_event("HEALTH_CHECK", "Health endpoint accessed")
    return {"status": "ok", "service": "saral-v1"}

@app.get("/version")
def version():
    return {"version": "v1.0.0", "commit": "v0.1-internal"}
