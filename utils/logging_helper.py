"""Logging utilities with correlation IDs and success/failure counters."""

import logging
import uuid
from contextvars import ContextVar

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)

class CorrelationIdFilter(logging.Filter):
    """Inject the correlation ID into all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get() or "N/A"
        return True

operation_counts = {"success": 0, "failure": 0}


def record_success() -> None:
    operation_counts["success"] += 1


def record_failure() -> None:
    operation_counts["failure"] += 1


def setup_logging(level: int = logging.INFO) -> str:
    """Configure root logging and generate a correlation ID.

    Returns the generated correlation ID so callers can include it elsewhere if
    needed.
    """
    cid = uuid.uuid4().hex
    correlation_id_var.set(cid)

    root = logging.getLogger()
    root.setLevel(level)

    if not root.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s [%(correlation_id)s] %(levelname)s %(name)s: %(message)s"
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)

    root.addFilter(CorrelationIdFilter())
    return cid
