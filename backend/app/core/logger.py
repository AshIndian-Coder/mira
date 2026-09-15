from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from typing import Optional

_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    """Compact JSON log line: ts | level | logger | message | extra."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_data", None)
        if extra:
            payload["data"] = extra
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: Optional[str] = None, log_file: Optional[str] = None) -> None:
    """Configure root logging (idempotent)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    from app.config import settings

    level_name = (level or settings.LOG_LEVEL).upper()
    file_path = log_file or settings.LOG_FILE

    root = logging.getLogger()
    root.setLevel(getattr(logging, level_name, logging.INFO))

    console = logging.StreamHandler(stream=sys.stdout)
    console.setFormatter(_JsonFormatter())
    root.addHandler(console)

    try:
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            file_path,
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
        )
        file_handler.setFormatter(_JsonFormatter())
        root.addHandler(file_handler)
    except OSError:  # pragma: no cover - read-only FS etc.
        root.warning("Could not open log file %s; console logging only", file_path)

    for noisy in ("uvicorn.access", "httpx", "pymilvus", "passlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Get a namespaced logger (e.g. get_logger("mira.matching"))."""
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(name)


def log_extra(logger: logging.Logger, level: int, msg: str, **data) -> None:
    """Log with structured extra fields: log_extra(log, INFO, "match done", pair=(1,2))."""

    class _Extra:
        pass

    record = logger.makeRecord(
        logger.name, level, "(none)", 0, msg, (), None
    )
    record.extra_data = data
    logger.handle(record)
