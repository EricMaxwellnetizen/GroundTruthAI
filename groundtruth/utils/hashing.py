from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from enum import Enum
from typing import Any


def _default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return str(value)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=_default)


def sha256_hex(value: Any) -> str:
    data = value if isinstance(value, bytes) else canonical_json(value).encode("utf-8")
    return hashlib.sha256(data).hexdigest()
