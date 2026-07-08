import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from .config import get_settings

logger = logging.getLogger("ai_layer.dead_letter")
_lock = threading.Lock()


def write_dead_letter(record_type: str, payload: dict) -> None:
    """record_type: 'message' | 'feedback'. payload: JSON-serializable dict, typically
    obtained via SomeSchema.model_dump(mode='json'). Appends one JSON line so nothing
    is silently lost if /messages/ or /feedback/ is briefly unreachable. Format is
    designed for a human/ops process to later read and manually replay each line
    against the API -- no automated replay tool is built (out of scope)."""
    settings = get_settings()
    path = Path(settings.dead_letter_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "record_type": record_type,
        "payload": payload,
        "failed_at": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    logger.error("Wrote dead-letter record type=%s to %s", record_type, path)
