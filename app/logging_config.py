import logging, sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("saral")

def log_event(action: str, detail: str):
    logger.info(f"{action} | {detail}")
