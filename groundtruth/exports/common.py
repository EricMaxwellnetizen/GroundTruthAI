from __future__ import annotations

import re
from typing import Any

from groundtruth.models.lineage import LineageResult
from groundtruth.models.report import EvidenceBundle
from groundtruth.utils.redaction import (
    SENSITIVE_KEY_PATTERN,
    redact_account_id,
    safe_text,
    strip_sensitive_url_parts,
)

ARN_ACCOUNT = re.compile(r"(arn:[^:]+:[^:]+:[^:]*:)(\d{12})(:.*)")
ENCODED_ARN_ACCOUNT = re.compile(r"(?i)(%3a)(\d{12})(?=%3a)")
STANDALONE_ACCOUNT = re.compile(r"(?<![0-9A-Za-z])(\d{12})(?![0-9A-Za-z])")


def redact_arn(value: str) -> str:
    return ARN_ACCOUNT.sub(
        lambda match: f"{match.group(1)}{redact_account_id(match.group(2))}{match.group(3)}",
        value,
    )


def redact_text(value: str) -> str:
    cleaned = strip_sensitive_url_parts(value)
    cleaned = redact_arn(cleaned)
    cleaned = ENCODED_ARN_ACCOUNT.sub(
        lambda match: f"{match.group(1)}{redact_account_id(match.group(2))}",
        cleaned,
    )
    cleaned = STANDALONE_ACCOUNT.sub(lambda match: redact_account_id(match.group(1)), cleaned)
    return safe_text(cleaned, limit=4000)


def redact_value(value: Any, key: str | None = None) -> Any:
    if key and SENSITIVE_KEY_PATTERN.search(key):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(item_key): redact_value(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact_value(item, key) for item in value]
    if isinstance(value, str):
        if key == "account_id":
            return redact_account_id(value)
        if key is not None and (key == "arn" or key.endswith("_arn")):
            return redact_arn(redact_text(value))
        return redact_text(value)
    return value


def build_evidence_bundle(
    result: LineageResult,
    *,
    redact: bool = True,
) -> EvidenceBundle:
    bundle = EvidenceBundle.from_lineage(result, redaction_applied=redact)
    if not redact:
        return bundle
    payload = bundle.model_dump(mode="json", exclude={"integrity"})
    redacted_payload = redact_value(payload)
    if isinstance(redacted_payload, dict):
        resource = redacted_payload.get("resource")
        if isinstance(resource, dict) and isinstance(resource.get("tags"), dict):
            redacted_payload["resource"] = resource
        redacted = EvidenceBundle(**redacted_payload)
        redacted.attach_checksum()
        return redacted
    return bundle
