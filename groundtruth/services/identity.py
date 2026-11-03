from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from groundtruth.models.enums import MatchType
from groundtruth.models.resource import CloudResource

ARN_PATTERN = re.compile(
    r"^arn:(?P<partition>aws(?:-[a-z]+)?):lambda:(?P<region>[a-z0-9-]+):(?P<account>\d{12}):function:(?P<name>[A-Za-z0-9_-]{1,64})(?::(?P<qualifier>[A-Za-z0-9_$-]{1,128}))?$"
)
NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class IdentityError(ValueError):
    pass


@dataclass(frozen=True)
class LambdaArn:
    partition: str
    region: str
    account_id: str
    function_name: str
    qualifier: str | None = None

    @property
    def arn(self) -> str:
        base = f"arn:{self.partition}:lambda:{self.region}:{self.account_id}:function:{self.function_name}"
        return f"{base}:{self.qualifier}" if self.qualifier else base


def parse_lambda_arn(arn: str) -> LambdaArn:
    text = (arn or "").strip()
    match = ARN_PATTERN.match(text)
    if not match:
        raise IdentityError("Enter a full Lambda ARN such as arn:aws:lambda:<region>:<account>:function:<name>.")
    return LambdaArn(
        partition=match.group("partition"),
        region=match.group("region"),
        account_id=match.group("account"),
        function_name=match.group("name"),
        qualifier=match.group("qualifier"),
    )


def is_lambda_arn(value: str | None) -> bool:
    if not value:
        return False
    return bool(ARN_PATTERN.match(value.strip()))


def normalize_lambda_identity(
    function: dict[str, Any],
    *,
    region: str,
    account_id: str,
    fixture: bool = False,
    observed_at: datetime | None = None,
) -> CloudResource:
    arn = function.get("FunctionArn") or function.get("arn") or function.get("resource_arn")
    name = function.get("FunctionName") or function.get("name") or function.get("resource_name")
    if not name:
        raise IdentityError("AWS Lambda response did not include a FunctionName.")
    if arn:
        try:
            parsed = parse_lambda_arn(arn)
            region = parsed.region
            account_id = parsed.account_id
            name = parsed.function_name
        except IdentityError:
            arn = None
    if not NAME_PATTERN.match(str(name)):
        raise IdentityError("Lambda function name contains unsupported characters.")
    tags = function.get("tags") or function.get("Tags") or {}
    last_modified = function.get("LastModified") or function.get("last_modified_at")
    if isinstance(last_modified, str):
        try:
            last_modified = datetime.fromisoformat(last_modified.replace("Z", "+00:00"))
        except ValueError:
            last_modified = None
    safe_attributes = {
        "runtime": function.get("Runtime"),
        "handler": function.get("Handler"),
        "role": function.get("Role"),
        "memory_size": function.get("MemorySize"),
        "timeout": function.get("Timeout"),
        "package_type": function.get("PackageType"),
        "architectures": function.get("Architectures") or [],
        "last_update_status": function.get("LastUpdateStatus"),
        "code_sha256": function.get("CodeSha256"),
        "version": function.get("Version"),
        "description_present": bool(function.get("Description")),
        "environment_variable_count": len((function.get("Environment") or {}).get("Variables") or {}),
    }
    safe_attributes = {key: value for key, value in safe_attributes.items() if value not in (None, [])}
    return CloudResource(
        account_id=str(account_id),
        region=str(region),
        name=str(name),
        arn=arn or f"arn:aws:lambda:{region}:{account_id}:function:{name}",
        provider_id=str(name),
        observed_at=observed_at or datetime.now().astimezone(),
        status=function.get("State") or function.get("Configuration", {}).get("State"),
        last_modified_at=last_modified,
        tags={str(key): str(value) for key, value in tags.items()},
        safe_attributes=safe_attributes,
        fixture=fixture,
    )


def ensure_identity_context(
    resource: CloudResource,
    *,
    account_id: str | None,
    region: str | None,
) -> bool:
    return bool(account_id and region and resource.account_id == account_id and resource.region == region)


def match_external_identity(
    resource: CloudResource,
    *,
    external_id: str | None,
    name: str | None,
    account_id: str | None,
    region: str | None,
) -> tuple[bool, MatchType | None, str]:
    external = (external_id or "").strip()
    candidate_name = (name or "").strip()
    if external and resource.arn and external == resource.arn:
        return True, MatchType.EXACT_ARN, "External ID is the exact Lambda ARN."
    if external and is_lambda_arn(external):
        parsed = parse_lambda_arn(external)
        if parsed.account_id != resource.account_id or parsed.region != resource.region:
            return False, None, "External ARN belongs to a different account or region."
        if parsed.function_name != resource.name:
            return False, None, "External ARN names a different function."
        return True, MatchType.EXACT_ARN, "External ID is the exact Lambda ARN."
    if candidate_name and candidate_name != resource.name:
        return False, None, "Function name does not match."
    if account_id and region:
        if account_id != resource.account_id or region != resource.region:
            return False, None, "Account or region context does not match."
        if external == resource.name or candidate_name == resource.name:
            return True, MatchType.EXACT_PROVIDER_ID, "Function name matches with exact account and region context."
    if external == resource.name or candidate_name == resource.name:
        return False, None, "Name matches but account/region context is missing or different."
    return False, None, "No exact identity match."
