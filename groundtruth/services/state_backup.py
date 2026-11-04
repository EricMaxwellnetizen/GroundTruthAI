from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from groundtruth.models.enums import ConfidenceLabel, MatchType
from groundtruth.models.resource import CloudResource
from groundtruth.models.state_backup import StateBackupEvidence, StateBackupMatch
from groundtruth.utils.hashing import sha256_hex
from groundtruth.utils.redaction import safe_text

MAX_STATE_BYTES = 8 * 1024 * 1024
MAX_RESOURCES = 20_000
MAX_MATCHES = 200
SUPPORTED_STATE_VERSIONS = {3, 4}

LIMITATIONS = [
    "User-supplied state snapshot; it is not independently verified against AWS or Scalr.",
    "A state snapshot is point-in-time evidence and does not prove current ownership.",
    "Raw state, outputs, module variables, environment values and secrets are discarded and never persisted.",
]


class StateBackupError(ValueError):
    pass


def _json_constant(value: str) -> Any:
    raise StateBackupError(f"State backup contained a non-finite JSON value: {value}.")


def _as_bytes(data: bytes | str | dict[str, Any]) -> bytes:
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return data.encode("utf-8")
    try:
        return json.dumps(data, ensure_ascii=True, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise StateBackupError("State backup could not be serialized safely.") from exc


def _text(value: Any, limit: int = 500) -> str | None:
    if value is None:
        return None
    text = safe_text(str(value), limit=limit).strip()
    return text or None


def _int(value: Any, *, minimum: int = 0, maximum: int = 1_000_000) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < minimum or value > maximum:
        return None
    return value


def _provider(value: Any) -> str | None:
    if isinstance(value, str):
        return _text(value, limit=300)
    if isinstance(value, list) and value:
        return _text(value[0], limit=300)
    return None


def _attributes(instance: dict[str, Any]) -> dict[str, Any]:
    raw = instance.get("attributes")
    return raw if isinstance(raw, dict) else {}


def _address(module: str | None, resource_type: str, name: str, instance: dict[str, Any], multi: bool) -> str:
    base = f"{resource_type}.{name}"
    if module:
        base = f"{module}.{base}"
    if not multi:
        return base
    index_key = instance.get("index_key")
    if isinstance(index_key, bool):
        return base
    if isinstance(index_key, int):
        return f"{base}[{index_key}]"
    if isinstance(index_key, str):
        return f'{base}["{safe_text(index_key, limit=120)}"]'
    return base


def _safe_architectures(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:4]:
        text = _text(item, limit=40)
        if text and text not in result:
            result.append(text)
    return result


def _match_types(
    target: CloudResource | None,
    *,
    arn: str | None,
    function_name: str | None,
) -> tuple[MatchType, ConfidenceLabel, str]:
    if target is None:
        return (
            MatchType.CANDIDATE_NAME,
            ConfidenceLabel.LOW,
            "Lambda function present in the supplied state; no target resource was supplied at parse time.",
        )
    target_arn = (target.arn or "").strip()
    if target_arn and arn and target_arn == arn:
        return (
            MatchType.EXACT_ARN,
            ConfidenceLabel.HIGH,
            "The supplied state contains the exact target Lambda ARN.",
        )
    if target_arn and arn and target_arn != arn:
        return (
            MatchType.CANDIDATE_NAME,
            ConfidenceLabel.LOW,
            "A Lambda function with the same name exists in another account, region or qualifier.",
        )
    if function_name and function_name == target.name:
        return (
            MatchType.CANDIDATE_NAME,
            ConfidenceLabel.LOW,
            "The function name matches, but the supplied state does not contain an exact target ARN.",
        )
    return (
        MatchType.CANDIDATE_NAME,
        ConfidenceLabel.LOW,
        "Lambda function present in the supplied state but not linked to the target identity.",
    )


def select_state_backup_match(
    backup: StateBackupEvidence | None,
    resource: CloudResource,
) -> tuple[StateBackupMatch, MatchType, ConfidenceLabel, str] | None:
    """Pick the safest state-backup match for one investigated resource.

    Exact ARN matches win. A name-only match is returned as a candidate and is
    never allowed to establish ownership. ARN conflicts are excluded entirely.
    """

    if backup is None:
        return None
    target_arn = (resource.arn or "").strip()
    name_matches: list[StateBackupMatch] = []
    for match in backup.matches:
        if target_arn and match.arn:
            if match.arn == target_arn:
                return (
                    match,
                    MatchType.EXACT_ARN,
                    ConfidenceLabel.HIGH,
                    "Exact ARN match in the user-supplied state snapshot.",
                )
            if match.function_name == resource.name:
                continue
        if match.function_name == resource.name:
            name_matches.append(match)
    if len(name_matches) == 1:
        return (
            name_matches[0],
            MatchType.CANDIDATE_NAME,
            ConfidenceLabel.LOW,
            "Name-only match in the user-supplied state snapshot; no exact ARN was available.",
        )
    if len(name_matches) > 1:
        return (
            name_matches[0],
            MatchType.CANDIDATE_NAME,
            ConfidenceLabel.LOW,
            "Multiple state addresses share this function name; the snapshot is ambiguous.",
        )
    return None


def parse_state_backup(
    data: bytes | str | dict[str, Any],
    *,
    filename: str,
    target: CloudResource | None = None,
) -> StateBackupEvidence:
    """Parse a Terraform state backup in memory and retain only safe identity fields."""

    raw_bytes = _as_bytes(data)
    if not raw_bytes:
        raise StateBackupError("State backup was empty.")
    if len(raw_bytes) > MAX_STATE_BYTES:
        raise StateBackupError(f"State backup exceeds the {MAX_STATE_BYTES // (1024 * 1024)} MB local parsing cap.")
    try:
        document = json.loads(raw_bytes.decode("utf-8"), parse_constant=_json_constant)
    except UnicodeDecodeError as exc:
        raise StateBackupError("State backup was not valid UTF-8.") from exc
    except json.JSONDecodeError as exc:
        raise StateBackupError("State backup was not valid JSON.") from exc
    if not isinstance(document, dict):
        raise StateBackupError("State backup must be a JSON object.")

    version = document.get("version")
    if isinstance(version, bool) or version not in SUPPORTED_STATE_VERSIONS:
        raise StateBackupError("Unsupported Terraform state version; expected version 3 or 4.")
    resources = document.get("resources")
    if not isinstance(resources, list):
        raise StateBackupError("State backup is missing a resources array.")
    if len(resources) > MAX_RESOURCES:
        raise StateBackupError("State backup contains too many resources to parse safely.")

    terraform_version = _text(document.get("terraform_version"), limit=80)
    serial = _int(document.get("serial"), minimum=0, maximum=2**63 - 1)
    lineage = _text(document.get("lineage"), limit=200)
    matches: list[StateBackupMatch] = []
    resource_count = 0
    for item in resources:
        if not isinstance(item, dict):
            continue
        resource_count += 1
        if item.get("type") != "aws_lambda_function":
            continue
        mode = _text(item.get("mode"), limit=20) or "managed"
        if mode != "managed":
            continue
        name = _text(item.get("name"), limit=120)
        if not name:
            continue
        module = _text(item.get("module"), limit=400)
        provider = _provider(item.get("provider"))
        instances = item.get("instances")
        if not isinstance(instances, list) or not instances:
            instances = [{}]
        multi = len(instances) > 1
        for instance in instances:
            if not isinstance(instance, dict):
                continue
            attrs = _attributes(instance)
            arn = _text(attrs.get("arn"), limit=2048)
            function_name = _text(attrs.get("function_name"), limit=64)
            match_type, confidence, reason = _match_types(target, arn=arn, function_name=function_name)
            matches.append(
                StateBackupMatch(
                    address=_address(module, "aws_lambda_function", name, instance, multi),
                    mode=mode,
                    name=name,
                    module=module,
                    provider=provider,
                    arn=arn,
                    function_name=function_name,
                    role_arn=_text(attrs.get("role"), limit=2048),
                    handler=_text(attrs.get("handler"), limit=160),
                    runtime=_text(attrs.get("runtime"), limit=80),
                    memory_size=_int(attrs.get("memory_size"), minimum=1, maximum=10240),
                    timeout=_int(attrs.get("timeout"), minimum=1, maximum=900),
                    architectures=_safe_architectures(attrs.get("architectures")),
                    last_modified=_text(attrs.get("last_modified"), limit=120),
                    match_type=match_type,
                    match_confidence=confidence,
                    match_reason=reason,
                )
            )
            if len(matches) >= MAX_MATCHES:
                break
        if len(matches) >= MAX_MATCHES:
            break

    limitations = list(LIMITATIONS)
    if version == 3:
        limitations.append("Legacy Terraform state version 3 was supplied.")
    if not matches:
        limitations.append("No managed aws_lambda_function resource was present in the supplied state.")

    return StateBackupEvidence(
        filename=safe_text(Path(filename).name or "state.json", limit=200),
        sha256=sha256_hex(raw_bytes),
        size_bytes=len(raw_bytes),
        terraform_version=terraform_version,
        state_version=int(version),
        serial=serial,
        lineage=lineage,
        resource_count=resource_count,
        matches=matches[:MAX_MATCHES],
        limitations=limitations,
    )
