import logging
import sys
from datetime import UTC, datetime
from typing import Any

import structlog


def add_timestamp(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    event_dict["timestamp"] = datetime.now(UTC).isoformat()
    return event_dict


def configure_logging() -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            add_timestamp,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
