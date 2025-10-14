# logging_config.py
import logging, sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / "saral.log"

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S"
)

root = logging.getLogger()
root.setLevel(logging.INFO)

# Console
ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(formatter)
root.addHandler(ch)

# Rotating file
fh = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
fh.setFormatter(formatter)
root.addHandler(fh)

logger = logging.getLogger("saral")

def log_event(action: str, detail: str):
    """Uniform event logging."""
    logger.info(f"ACTION={action} | {detail}")