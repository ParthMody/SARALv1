import logging
import json
from datetime import datetime

logger = logging.getLogger("saral")
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)


def log_event(action: str, message: str, extra: dict | None = None) -> None:
    payload = {"action": action, "message": message}
    if extra:
        payload.update(extra)
    logger.info(json.dumps(payload, default=str))


def log_failure(error_code: str, context: dict | None = None) -> dict:
    """
    Single entry point for failure logging.
    Returns a minimal payload you can also persist into Event.payload.
    """
    payload = {
        "error_code": error_code,
        "timestamp": datetime.utcnow().isoformat(),
    }
    if context:
        payload["context"] = context

    logger.error(json.dumps(payload, default=str))
    return payload


def log_export(export_id: str, operator_id: str | None, row_count: int) -> dict:
    payload = {
        "export_id": export_id,
        "operator_id": operator_id,
        "row_count": row_count,
        "timestamp": datetime.utcnow().isoformat(),
    }
    logger.info(json.dumps({"action": "EXPORT", **payload}, default=str))
    return payload
