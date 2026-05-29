"""Centralised logging configuration for GAWorld.

Why this module exists
----------------------
The legacy code base relies on ``print('⚠️ ...')`` calls for warnings.
That makes it impossible to:

* filter messages by severity,
* mirror everything to a log file for post-mortem,
* attach structured context (agent_id, day, stage) to every record.

This module wires up a single :class:`logging.Logger` tree under the
``gaworld`` namespace so that any module can do::

    from gaworld.logging_setup import get_logger
    log = get_logger(__name__)
    log.warning("schedule rejected", extra={"agent_id": 7})

Configuration is environment-driven so existing entry points keep
working without code changes:

* ``GAWORLD_LOG_LEVEL`` (default ``INFO``)
* ``GAWORLD_LOG_FILE``  – optional; defaults to ``output/logs/run.log``.
* ``GAWORLD_LOG_MODE``  – ``simple`` (default) or ``verbose``.

  ``simple``  — compact terminal output: no per-call LLM INFO lines,
                repeated warnings suppressed to once per 60 s, and the
                structured-context tail (agent=/day=/stage=) is hidden
                (those fields are still written to the log file).
  ``verbose`` — full structured output, identical to pre-S4 behaviour.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import time
from typing import Any

_CONFIGURED = False
_DEFAULT_LOG_PATH = os.path.join("output", "logs", "run.log")

# Read once at import time so the mode is stable for the whole process.
LOG_MODE: str = os.environ.get("GAWORLD_LOG_MODE", "simple").strip().lower()


class _ContextFilter(logging.Filter):
    """Ensure every record has the structured-context keys we use."""

    _KEYS = ("agent_id", "day", "stage", "provider", "task")

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        for key in self._KEYS:
            if not hasattr(record, key):
                setattr(record, key, "")
        return True


class _DeduplicateFilter(logging.Filter):
    """Suppress repeated identical WARNING/INFO messages within a cooldown.

    Used in simple mode to avoid flooding the terminal with the same
    connection-refused warning on every simulation tick.
    ERROR and CRITICAL messages always pass through unchanged.
    """

    def __init__(self, cooldown_seconds: float = 60.0) -> None:
        super().__init__()
        self._cooldown = cooldown_seconds
        self._last_seen: dict[str, float] = {}

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR:
            return True
        # Key on logger name + level + first 120 chars of the message template
        # (not the formatted string, to catch parameterised repeats cheaply).
        key = f"{record.name}:{record.levelno}:{str(record.msg)[:120]}"
        now = time.monotonic()
        if now - self._last_seen.get(key, 0.0) < self._cooldown:
            return False
        self._last_seen[key] = now
        return True


def _resolve_level(value: str | int | None) -> int:
    if isinstance(value, int):
        return value
    text = str(value or "INFO").strip().upper() or "INFO"
    return getattr(logging, text, logging.INFO)


def configure_logging(
    *,
    level: str | int | None = None,
    log_file: str | None = None,
    force: bool = False,
) -> logging.Logger:
    """Initialise the ``gaworld`` logger tree.

    Idempotent: subsequent calls are no-ops unless ``force=True``.

    Returns the configured root logger for the ``gaworld`` namespace.
    """
    global _CONFIGURED
    root = logging.getLogger("gaworld")
    if _CONFIGURED and not force:
        return root

    level = _resolve_level(level if level is not None else os.environ.get("GAWORLD_LOG_LEVEL"))
    root.setLevel(level)
    root.handlers.clear()
    root.propagate = False

    context_filter = _ContextFilter()

    # Simple mode: strip the always-empty agent=/day=/stage= tail from the
    # terminal stream (it still appears in the file for post-mortem analysis).
    if LOG_MODE == "simple":
        stream_fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    else:
        stream_fmt = (
            "%(asctime)s | %(levelname)-7s | %(name)s"
            " | agent=%(agent_id)s day=%(day)s stage=%(stage)s"
            " | %(message)s"
        )
    stream_formatter = logging.Formatter(stream_fmt, datefmt="%H:%M:%S")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(stream_formatter)
    stream_handler.addFilter(context_filter)
    if LOG_MODE == "simple":
        # Suppress repeated identical warnings (e.g. env-server unreachable).
        stream_handler.addFilter(_DeduplicateFilter(cooldown_seconds=60.0))
    root.addHandler(stream_handler)

    # File handler always uses the full structured format.
    file_fmt = (
        "%(asctime)s | %(levelname)-7s | %(name)s"
        " | agent=%(agent_id)s day=%(day)s stage=%(stage)s"
        " | %(message)s"
    )
    file_formatter = logging.Formatter(file_fmt, datefmt="%Y-%m-%d %H:%M:%S")
    target = log_file if log_file is not None else os.environ.get("GAWORLD_LOG_FILE")
    if target is None:
        target = _DEFAULT_LOG_PATH
    target = str(target).strip()
    if target:
        try:
            log_dir = os.path.dirname(target)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                target, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
            file_handler.setFormatter(file_formatter)
            file_handler.addFilter(context_filter)
            root.addHandler(file_handler)
        except OSError:
            root.warning("Failed to attach file handler at %s", target)

    if LOG_MODE == "simple":
        # Per-call LLM INFO lines (ok/err) are useful in verbose mode but noisy
        # in simple mode.  Raise the floor for that sub-logger so only warnings
        # and errors surface on the terminal.
        logging.getLogger("gaworld.llm").setLevel(logging.WARNING)

    _CONFIGURED = True
    return root


def get_logger(name: str | None = None, **context: Any) -> logging.LoggerAdapter:
    """Return a context-aware logger.

    The returned :class:`LoggerAdapter` injects ``agent_id`` / ``day`` /
    ``stage`` / ``provider`` / ``task`` keys into every record, so the
    formatter can render them uniformly.
    """
    configure_logging()
    base = logging.getLogger(name or "gaworld")
    extra = {"agent_id": "", "day": "", "stage": "", "provider": "", "task": ""}
    extra.update({k: v for k, v in context.items() if v is not None})
    return logging.LoggerAdapter(base, extra)
