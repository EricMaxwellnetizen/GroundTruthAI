from __future__ import annotations

import json
from datetime import datetime

from groundtruth.exports.common import build_evidence_bundle
from groundtruth.models.lineage import LineageResult
from groundtruth.models.report import EvidenceBundle


def export_json(
    result: LineageResult,
    *,
    redact: bool = True,
    exported_at: datetime | None = None,
) -> tuple[str, EvidenceBundle]:
    bundle = build_evidence_bundle(result, redact=redact)
    if exported_at is not None:
        bundle.exported_at = exported_at
        bundle.attach_checksum()
    text = json.dumps(
        bundle.model_dump(mode="json"),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )
    return text, bundle


def export_json_safe(result: LineageResult, *, redact: bool = True) -> str:
    return export_json(result, redact=redact)[0]
