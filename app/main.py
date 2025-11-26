# app/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .db import Base, engine, SessionLocal
from . import models
from .routes import cases, metrics, dashboard, events, ai, export, ops # Added ops
from app.logging_config import log_event

app = FastAPI(title="SARAL v1 API")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

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

# Routers
app.include_router(cases.router)
app.include_router(ops.router) # NEW: Operations Router
app.include_router(metrics.router)
app.include_router(dashboard.router)
app.include_router(events.router)
app.include_router(ai.router)   
app.include_router(export.router)

@app.get("/")
def health():
    return {"status": "ok", "service": "saral-v1"}