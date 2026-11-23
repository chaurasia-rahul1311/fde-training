import logging
import json
from datetime import datetime, timezone
import os
from typing import Any, Literal

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("task_assistant.log"),
    ],
)

audit_logger = logging.getLogger("task_assistant.audit")


def log_audit(
    request_id: str,
    user_id: str | int | None,
    action: str,
    status: Literal[
        "SUCCESS",
        "DENIED",
        "PENDING_CONFIRMATION",
        "VALIDATION_ERROR",
        "TOOL_ERROR",
        "LLM_REQUEST",
    ],
    details: dict[str, Any],
) -> None:

    log = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "user_id": "" if user_id is None else str(user_id),
        "action": action,
        "status": status,
        "details": details,
    }
    audit_logger.info(json.dumps(log, default=str))
