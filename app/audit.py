# app/audit.py
"""
Central helper for writing to audit_log.
All routes call log_event() — never insert into audit_log directly.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from .models import AuditLog, AuditActionEnum


def log_event(
    db: Session,
    action: AuditActionEnum,
    *,
    actor_id: str | None = None,
    session_id: str | None = None,
    case_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        actor_id=actor_id or "SYSTEM",
        session_id=session_id,
        case_id=case_id,
        payload=json.dumps(payload or {}, ensure_ascii=False, default=str),
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry