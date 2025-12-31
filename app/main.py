# app/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from sqlalchemy import text
from .db import Base, engine, SessionLocal
from . import models
from .routes import cases, metrics, dashboard, events, ai, export, ops


def _sqlite_add_column_if_missing(table: str, column: str, coltype: str) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.connect() as conn:
        cols = conn.execute(text(f"PRAGMA table_info({table});")).fetchall()
        existing = {row[1] for row in cols}
        if column not in existing:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype};"))
            conn.commit()


def _apply_schema_patches() -> None:
    # EVENTS TABLE (defensive patches for older DBs)
    _sqlite_add_column_if_missing("events", "case_id", "TEXT")
    _sqlite_add_column_if_missing("events", "action", "TEXT")
    _sqlite_add_column_if_missing("events", "actor_type", "TEXT")
    _sqlite_add_column_if_missing("events", "payload", "TEXT")
    _sqlite_add_column_if_missing("events", "app_version", "TEXT")
    _sqlite_add_column_if_missing("events", "schema_version", "TEXT")
    _sqlite_add_column_if_missing("events", "created_at", "DATETIME")
    _sqlite_add_column_if_missing("events", "updated_at", "DATETIME")

    # CASES TABLE (defensive patches)
    _sqlite_add_column_if_missing("cases", "app_version", "TEXT")
    _sqlite_add_column_if_missing("cases", "ruleset_version", "TEXT")
    _sqlite_add_column_if_missing("cases", "model_version", "TEXT")
    _sqlite_add_column_if_missing("cases", "schema_version", "TEXT")
    _sqlite_add_column_if_missing("cases", "session_id", "TEXT")
    _sqlite_add_column_if_missing("cases", "meta_duration_seconds", "INTEGER")
    _sqlite_add_column_if_missing("cases", "arm", "TEXT")
    _sqlite_add_column_if_missing("cases", "ai_shown", "BOOLEAN")
    _sqlite_add_column_if_missing("cases", "assignment_reason", "TEXT")


def _ensure_db_ready() -> None:
    # CRITICAL: guaranteed schema init for pytest + local runs
    Base.metadata.create_all(bind=engine)
    _apply_schema_patches()


# Run schema init at import time so pytest cannot bypass it
_ensure_db_ready()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Keep this for safety + seeding (but tables already exist now)
    _ensure_db_ready()

    db = SessionLocal()
    try:
        # Seed schemes (idempotent)
        if not db.query(models.Scheme).first():
            db.add_all(
                [
                    models.Scheme(code="UJJ", name="PM Ujjwala Yojana"),
                    models.Scheme(code="PMAY", name="PM Awas Yojana"),
                ]
            )
            db.commit()
    finally:
        db.close()

    yield


app = FastAPI(title="SARAL v1 API", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(cases.router)
app.include_router(ops.router)
app.include_router(metrics.router)
app.include_router(dashboard.router)
app.include_router(events.router)
app.include_router(ai.router)
app.include_router(export.router)


@app.get("/")
def health():
    return {"status": "ok", "service": "saral-v1"}
