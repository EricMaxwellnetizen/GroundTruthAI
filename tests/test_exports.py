from __future__ import annotations

import json

import pytest

from groundtruth.exports import build_evidence_bundle, export_json, export_markdown
from groundtruth.exports.common import redact_text
from groundtruth.services.orchestrator import InvestigationOrchestrator

CASES = [
    "A_historical_owner",
    "B_multiple_active_owners",
    "C_candidate_lineage",
    "D_insufficient_access",
    "E_current_owner",
]


def _result(settings, case_id: str):
    return InvestigationOrchestrator(settings).run_fixture(case_id)


@pytest.mark.parametrize("case_id", CASES)
def test_json_bundle_is_checksummed_and_redacted(settings, case_id: str) -> None:
    result = _result(settings, case_id)
    text, bundle = export_json(result, redact=True)
    assert bundle.integrity is not None
    assert bundle.verify_checksum() is True
    assert bundle.redaction_applied is True
    payload = json.loads(text)
    assert payload["bundle_type"] == "groundtruth.evidence_bundle"
    assert payload["fixture"] is True
    assert payload["mode"] == "fixture"
    assert "123456789012" not in text
    assert "********9012" in text
    parsed = json.loads(text)
    assert parsed["integrity"]["checksum"] == bundle.integrity.checksum


@pytest.mark.parametrize("case_id", CASES)
def test_markdown_report_is_labelled_and_cites_evidence(settings, case_id: str) -> None:
    result = _result(settings, case_id)
    text, bundle = export_markdown(result, redact=True)
    assert bundle.verify_checksum() is True
    assert "GroundTruth Evidence Report" in text
    assert "DEMO / FIXTURE DATA" in text
    assert result.status.value in text
    assert result.investigation_id in text
    assert "123456789012" not in text
    assert "Integrity" in text
    assert "sha256:" in text
    assert "Coverage" in text


def test_account_redaction_does_not_corrupt_alphanumeric_identifiers() -> None:
    assert redact_text("inv_a49a593875404981") == "inv_a49a593875404981"
    assert redact_text("123456789012") == "********9012"
    encoded_arn = "arn%3Aaws%3Alambda%3Aap-south-1%3A123456789012%3Afunction%3Aorders"
    assert "123456789012" not in redact_text(encoded_arn)


def test_redaction_can_be_disabled_for_local_analysis(settings) -> None:
    result = _result(settings, "E_current_owner")
    text, bundle = export_json(result, redact=False)
    assert bundle.redaction_applied is False
    assert "123456789012" in text
    assert bundle.verify_checksum() is True


def test_bundle_round_trip_and_manual_edit_detection(settings) -> None:
    result = _result(settings, "E_current_owner")
    bundle = build_evidence_bundle(result, redact=True)
    payload = bundle.model_dump(mode="json")
    assert bundle.verify_checksum() is True
    payload["status_reason"] = "tampered"
    from groundtruth.models.report import EvidenceBundle

    tampered = EvidenceBundle(**payload)
    assert tampered.verify_checksum() is False


def test_redact_text_strips_url_credentials_and_accounts() -> None:
    text = redact_text(
        "https://user:password@example.com/path?token=abc&x=1 arn:aws:lambda:ap-south-1:123456789012:function:orders"
    )
    assert "password" not in text
    assert "token=abc" not in text
    assert "123456789012" not in text
    assert "********9012" in text


def test_export_contains_no_aws_key_material(settings) -> None:
    result = _result(settings, "E_current_owner")
    text, _ = export_json(result, redact=True)
    assert "AKIA" not in text
    assert "aws_secret_access_key" not in text
    assert "SCALR_API_TOKEN" not in text
    assert "MODEL_API_KEY" not in text
