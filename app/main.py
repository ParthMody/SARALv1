# app/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .db import Base, engine
from . import models  # noqa: F401 — ensures all models are registered with Base


def _ensure_db_ready() -> None:
    """Create all tables if they don't exist. Safe to call on every startup."""
    Base.metadata.create_all(bind=engine)


# Run at import time so pytest and local runs both get a schema
_ensure_db_ready()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Re-run at startup (harmless if tables exist)
    _ensure_db_ready()
    yield


app = FastAPI(
    title="SARAL v2 — Experimental Instrument",
    version="2.0.0-dev",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ── Route registration ───────────────────────────────────────────────────────
from .routes import dashboard  # noqa: E402
from .routes import session    # noqa: E402

app.include_router(dashboard.router)
app.include_router(session.router)

# from .routes import admin     # researcher/admin panel
# from .routes import export    # CSV / SQLite export
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {"status": "ok", "service": "saral-v2", "version": "2.0.0-dev"}