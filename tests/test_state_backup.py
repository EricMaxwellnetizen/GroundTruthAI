from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from groundtruth.connectors import FixtureCaseLoader
from groundtruth.exports import export_json
from groundtruth.models.connector import ConnectorResult
from groundtruth.models.enums import ConfidenceLabel, ConnectorStatus, LineageStatus, MatchType
from groundtruth.models.lineage import ScalrDataset
from groundtruth.models.resource import CloudResource
from groundtruth.services.lineage_engine import LineageEngine
from groundtruth.services.state_backup import (
    StateBackupError,
    parse_state_backup,
    select_state_backup_match,
)

ARN = "arn:aws:lambda:ap-south-1:123456789012:function:orders-transformer"
ROLE = "arn:aws:iam::123456789012:role/orders-transformer-role"


def _resource(arn: str | None = ARN, name: str = "orders-transformer") -> CloudResource:
    return CloudResource(
        account_id="123456789012",
        region="ap-south-1",
        name=name,
        arn=arn,
        provider_id=name,
        observed_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )


def _state(*, arn: str | None = ARN, function_name: str = "orders-transformer", instances: int = 1) -> dict:
    state_instances = []
    for index in range(instances):
        attributes = {
            "arn": arn,
            "function_name": function_name,
            "role": ROLE,
            "handler": "handler.main",
            "runtime": "python3.12",
            "memory_size": 512,
            "timeout": 30,
            "architectures": ["x86_64"],
            "last_modified": "2026-09-08T10:15:00.000+0000",
            "environment": [{"variables": {"DB_PASSWORD": "environment-secret"}}],
            "source_code_hash": "source-hash-secret",
        }
        state_instances.append(
            {
                "index_key": index if instances > 1 else None,
                "attributes": attributes,
                "sensitive_attributes": [{"type": "get_attr", "value": "secret"}],
            }
        )
    return {
        "version": 4,
        "terraform_version": "1.9.5",
        "serial": 42,
        "lineage": "lineage-abc",
        "outputs": {"database_password": {"value": "output-secret", "type": "string"}},
        "resources": [
            {
                "mode": "managed",
                "type": "aws_lambda_function",
                "name": "transformer",
                "provider": 'provider["registry.terraform.io/hashicorp/aws"]',
                "instances": state_instances,
            },
            {
                "mode": "managed",
                "type": "aws_s3_bucket",
                "name": "private",
                "instances": [{"attributes": {"bucket": "private-bucket-secret"}}],
            },
        ],
    }


def _bytes(state: dict) -> bytes:
    return json.dumps(state).encode("utf-8")


def test_parser_keeps_only_lambda_identity_and_redacts_raw_state() -> None:
    backup = parse_state_backup(_bytes(_state()), filename="prod.tfstate", target=_resource())
    assert backup.state_version == 4
    assert backup.terraform_version == "1.9.5"
    assert backup.serial == 42
    assert backup.resource_count == 2
    assert len(backup.matches) == 1
    match = backup.matches[0]
    assert match.address == "aws_lambda_function.transformer"
    assert match.arn == ARN
    assert match.function_name == "orders-transformer"
    assert match.match_type == MatchType.EXACT_ARN
    assert match.match_confidence == ConfidenceLabel.HIGH
    assert match.origin == "user_supplied"
    dumped = backup.model_dump_json()
    for secret in (
        "environment-secret",
        "DB_PASSWORD",
        "output-secret",
        "private-bucket-secret",
        "source-hash-secret",
        "sensitive_attributes",
    ):
        assert secret not in dumped


def test_parser_handles_count_addresses() -> None:
    backup = parse_state_backup(_bytes(_state(instances=2)), filename="count.tfstate")
    addresses = [match.address for match in backup.matches]
    assert addresses == ["aws_lambda_function.transformer[0]", "aws_lambda_function.transformer[1]"]


def test_parser_without_target_returns_candidates() -> None:
    backup = parse_state_backup(_bytes(_state()), filename="prod.tfstate")
    assert backup.matches[0].match_type == MatchType.CANDIDATE_NAME
    assert backup.matches[0].match_confidence == ConfidenceLabel.LOW


def test_selection_prefers_exact_arn_and_rejects_conflicts() -> None:
    backup = parse_state_backup(_bytes(_state()), filename="prod.tfstate")
    selected = select_state_backup_match(backup, _resource())
    assert selected is not None
    assert selected[1] == MatchType.EXACT_ARN
    conflict = _resource(arn=ARN.replace("123456789012", "999999999999"))
    assert select_state_backup_match(backup, conflict) is None
    name_only = select_state_backup_match(backup, _resource(arn=None))
    assert name_only is not None
    assert name_only[1] == MatchType.CANDIDATE_NAME


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"not-json",
        b'{"version": 2, "resources": []}',
        b'{"version": 4}',
        b'{"version": 4, "resources": {}}',
        b'{"version": 4, "resources": [], "serial": NaN}',
        b"\xff\xfe\x00",
    ],
)
def test_parser_rejects_malformed_or_unsupported_state(payload: bytes) -> None:
    with pytest.raises(StateBackupError):
        parse_state_backup(payload, filename="bad.tfstate")


def test_parser_rejects_oversized_state() -> None:
    with pytest.raises(StateBackupError):
        parse_state_backup(b"x" * (8 * 1024 * 1024 + 1), filename="huge.tfstate")


def test_parser_sanitizes_filename() -> None:
    backup = parse_state_backup(_bytes(_state()), filename="../../etc/passwd.tfstate")
    assert backup.filename == "passwd.tfstate"


def _fixture_case(settings, case_id: str = "E_current_owner"):
    return FixtureCaseLoader(settings).load(case_id)


def _investigate(settings, case, *, scalr_result=None, state_backup=None):
    return LineageEngine(settings).investigate(
        case.resource,
        aws_result=case.aws_result,
        scalr_result=scalr_result or case.scalr_result,
        git_lineage=None,
        git_result=None,
        cloudtrail_result=case.cloudtrail_result,
        cloudwatch_result=case.cloudwatch_result,
        omni_result=case.omni_result,
        mode="fixture",
        state_backup=state_backup,
    )


def test_uploaded_state_cannot_override_live_current_owner(settings) -> None:
    case = _fixture_case(settings)
    backup = parse_state_backup(_bytes(_state()), filename="prod.tfstate")
    result = _investigate(settings, case, state_backup=backup)
    assert result.status == LineageStatus.CURRENT_OWNER_FOUND
    assert result.current_owners
    assert result.state_backup is backup
    assert any(item.source.value == "terraform_state_backup" for item in result.evidence)
    assert any(record.source == "terraform_state_backup" for record in result.coverage)


def test_uploaded_state_produces_candidate_when_live_state_is_empty(settings) -> None:
    case = _fixture_case(settings)
    empty_scalr = ConnectorResult(status=ConnectorStatus.SUCCESS, source="scalr", data=ScalrDataset(), fixture=True)
    backup = parse_state_backup(_bytes(_state()), filename="prod.tfstate")
    result = _investigate(settings, case, scalr_result=empty_scalr, state_backup=backup)
    assert result.status == LineageStatus.CANDIDATE_LINEAGE
    assert result.confidence == ConfidenceLabel.MEDIUM
    assert "user-supplied" in result.status_reason.lower()
    state_evidence = next(item for item in result.evidence if item.source.value == "terraform_state_backup")
    assert state_evidence.origin == "user_supplied"
    assert state_evidence.match_type == MatchType.EXACT_ARN


def test_uploaded_state_cannot_override_insufficient_access(settings) -> None:
    case = _fixture_case(settings, "D_insufficient_access")
    backup = parse_state_backup(_bytes(_state()), filename="prod.tfstate")
    result = _investigate(settings, case, state_backup=backup)
    assert result.status == LineageStatus.INSUFFICIENT_ACCESS
    assert result.confidence == ConfidenceLabel.UNKNOWN


def test_state_backup_is_exported_and_redacted(settings) -> None:
    case = _fixture_case(settings)
    backup = parse_state_backup(_bytes(_state()), filename="prod.tfstate")
    result = _investigate(settings, case, state_backup=backup)
    text, bundle = export_json(result, redact=True)
    assert bundle.state_backup is not None
    assert bundle.verify_checksum()
    assert "123456789012" not in text
    assert '"state_backup"' in text
    assert "environment-secret" not in text
    assert "output-secret" not in text
