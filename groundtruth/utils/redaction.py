from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(secret|token|password|passwd|private[_-]?key|api[_-]?key|access[_-]?key|credential|authorization|auth[_-]?key)"
)
UNSAFE_TEXT_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
LONG_TEXT_LIMIT = 800


def redact_account_id(account_id: str | None) -> str:
    if not account_id:
        return ""
    text = str(account_id)
    if len(text) <= 4:
        return "*" * len(text)
    return "*" * (len(text) - 4) + text[-4:]


def redact_identifier(value: str | None, keep_last: int = 4) -> str:
    if not value:
        return ""
    text = str(value)
    if len(text) <= keep_last:
        return "*" * len(text)
    return "*" * (len(text) - keep_last) + text[-keep_last:]


def redact_tags(tags: dict[str, Any] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in (tags or {}).items():
        key_text = safe_text(str(key), limit=120)
        if SENSITIVE_KEY_PATTERN.search(key_text):
            result[key_text] = "[redacted]"
        else:
            result[key_text] = safe_text(str(value), limit=200)
    return result


def safe_text(value: str, limit: int = LONG_TEXT_LIMIT) -> str:
    cleaned = UNSAFE_TEXT_PATTERN.sub("", value or "")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    if len(cleaned) > limit:
        return cleaned[: limit - 1] + "…"
    return cleaned


def strip_sensitive_url_parts(url: str) -> str:
    cleaned = re.sub(r"(?i)([a-z][a-z0-9+.-]*://)[^/\s@]+@", r"\1[redacted]@", url)
    return re.sub(r"(?i)([?&](?:token|key|secret|password|sig|signature)=)[^&]+", r"\1[redacted]", cleaned)
