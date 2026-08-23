"""Structured logging setup (plan § 23.1).

Provides a ``get_logger`` helper that adds the ``service`` key and a
``StructuredFormatter`` that emits JSON-compatible log records with unified
context fields: timestamp, level, service, trace_id, request_id, incident_id,
diagnosis_run_id, duration_ms, error_type.

Usage:
    from app.observability import get_logger
    logger = get_logger(__name__)  # same signature as logging.getLogger
"""

import json
import logging
import sys
import time
from typing import Any

# Well-known context keys that appear in structured log output.
_TRACE_KEYS = (
    "trace_id",
    "request_id",
    "incident_id",
    "diagnosis_run_id",
    "evaluation_run_id",
    "tool_call_id",
    "duration_ms",
    "error_type",
)

_LOGGER_CACHE: dict[str, logging.Logger] = {}


class StructuredFormatter(logging.Formatter):
    """JSON-compatible log formatter that merges extra-context fields."""

    def format(self, record: logging.LogRecord) -> str:
        base: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in _TRACE_KEYS:
            val = getattr(record, key, None)
            if val is not None:
                base[key] = val
        if record.exc_info and record.exc_info[1]:
            base["exception"] = str(record.exc_info[1])[:500]
        return json.dumps(base, ensure_ascii=False, default=str)


def _configure_root() -> None:
    """Set up the root handler once so all loggers inherit structured output."""
    root = logging.getLogger()
    if root.handlers:
        return  # already configured
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)


_configure_root()


def get_logger(name: str) -> logging.Logger:
    """Return a logger with the ``service`` field pre-filled.

    In a FastAPI handler, augment with::

        from app.observability import add_context
        logger = add_context(logger, trace_id=request.state.trace_id)
    """
    if name not in _LOGGER_CACHE:
        logger = logging.getLogger(name)
        # Attach a log-adapter-like behaviour via a custom adapter.
        logger = _ContextAdapter(logger, {"service": "paytrace"})
        _LOGGER_CACHE[name] = logger
    return _LOGGER_CACHE[name]


class _ContextAdapter(logging.LoggerAdapter):
    """LoggerAdapter that merges extra dict into LogRecord __dict__."""

    def process(self, msg: Any, kwargs: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        extra = kwargs.get("extra", {})
        extra.update(self.extra or {})
        kwargs["extra"] = extra
        return msg, kwargs


def add_context(logger: logging.Logger, **ctx: Any) -> logging.Logger:
    """Return a logger with additional context fields merged in.

    Example:
        logger = add_context(logger, trace_id=req.state.trace_id, incident_id=str(incident_id))
    """
    if isinstance(logger, _ContextAdapter):
        merged = dict(logger.extra or {})
    else:
        merged = {}
    merged.update({k: v for k, v in ctx.items() if v is not None})
    return _ContextAdapter(logger.logger if isinstance(logger, _ContextAdapter) else logger, merged)


class TimingContext:
    """Context manager that logs duration_ms on exit."""

    def __init__(self, logger: logging.Logger, operation: str) -> None:
        self._logger = logger
        self._operation = operation
        self._start: float = 0.0

    def __enter__(self) -> "TimingContext":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        duration_ms = int((time.perf_counter() - self._start) * 1000)
        self._logger.info("%s completed", self._operation, extra={"duration_ms": duration_ms})
