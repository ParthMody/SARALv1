from fastapi import FastAPI
from .db import Base, engine, SessionLocal
from . import models
from .routes import cases
from .routes import metrics  # Add this import if metrics router exists

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

app.include_router(cases.router)
app.include_router(metrics.router)  # Only include once

@app.get("/")
def health():
    return {"status": "ok", "service": "saral-v1"}