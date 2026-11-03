from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

_SECRET_PATTERN = re.compile(
    r"(?i)(bearer\s+[a-z0-9\-._~+/]+=*|(?:api[_-]?key|token|secret|password)\s*[=:]\s*['\"]?[^\s'\"]+)"
)
_AWS_KEY_PATTERN = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")


def redact_text(value: str) -> str:
    value = _SECRET_PATTERN.sub("[redacted]", value)
    return _AWS_KEY_PATTERN.sub("[redacted-aws-key]", value)


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(str(record.getMessage()))
        record.args = ()
        return True


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(str(record.getMessage())),
        }
        for key in (
            "investigation_id",
            "connector",
            "stage",
            "status",
            "duration_ms",
            "pages",
            "records",
            "error_class",
            "source",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["error_class"] = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
            payload["error"] = redact_text(str(record.exc_info[1]))
        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_logging(level: str = "INFO", debug: bool = False) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(StructuredFormatter())
    handler.addFilter(RedactionFilter())
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if debug else getattr(logging, level.upper(), logging.INFO))
    for noisy in ("botocore", "boto3", "urllib3", "httpx", "openai", "watchdog", "streamlit"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
