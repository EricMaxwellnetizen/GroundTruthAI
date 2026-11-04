from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from groundtruth.exports import export_json
from groundtruth.services.orchestrator import InvestigationOrchestrator

CASES = [
    "A_historical_owner",
    "B_multiple_active_owners",
    "C_candidate_lineage",
    "D_insufficient_access",
    "E_current_owner",
]


@pytest.fixture(scope="module")
def bundle_schema(repo_root: Path) -> dict:
    schema_path = repo_root / "fixtures" / "schemas" / "evidence_bundle.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


@pytest.mark.parametrize("case_id", CASES)
def test_exported_bundle_matches_published_schema(settings, bundle_schema, case_id: str) -> None:
    result = InvestigationOrchestrator(settings).run_fixture(case_id)
    text, bundle = export_json(result, redact=True)
    payload = json.loads(text)
    Draft202012Validator(bundle_schema).validate(payload)
    assert payload["status"] == result.status.value
    assert payload["confidence"] == result.confidence.value
    assert payload["redaction_applied"] is True
    assert bundle.verify_checksum() is True
    assert payload["integrity"]["redaction_applied"] is True


def test_schema_rejects_an_unknown_status_or_malformed_checksum(settings, bundle_schema) -> None:
    result = InvestigationOrchestrator(settings).run_fixture("E_current_owner")
    payload = json.loads(export_json(result, redact=True)[0])
    validator = Draft202012Validator(bundle_schema)
    payload["status"] = "MADE_UP_STATUS"
    with pytest.raises(ValidationError):
        validator.validate(payload)
    payload["status"] = result.status.value
    payload["integrity"]["checksum"] = "not-a-checksum"
    with pytest.raises(ValidationError):
        validator.validate(payload)
