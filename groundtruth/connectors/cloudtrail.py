from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError, ProfileNotFound

from groundtruth.config import Settings
from groundtruth.connectors.base import BaseConnector, safe_error_message
from groundtruth.connectors.aws_lambda import _aws_status
from groundtruth.models.connector import ConnectionTest, ConnectorResult
from groundtruth.models.enums import ConnectorStatus, MatchType, PrincipalType
from groundtruth.utils.retry import RateLimiter


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def principal_type_from_identity(identity: dict[str, Any]) -> PrincipalType:
    value = str(identity.get("type") or "").strip()
    mapping = {
        "IAMUser": PrincipalType.IAM_USER,
        "AssumedRole": PrincipalType.ASSUMED_ROLE,
        "AWSService": PrincipalType.AWS_SERVICE,
        "Root": PrincipalType.ROOT,
        "FederatedUser": PrincipalType.FEDERATED_USER,
    }
    return mapping.get(value, PrincipalType.UNKNOWN)


def parse_cloudtrail_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    payload: dict[str, Any] = {}
    raw_json = raw.get("CloudTrailEvent")
    if isinstance(raw_json, str) and raw_json.strip():
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            payload = {}
    if not payload:
        payload = dict(raw)
    event_time = _parse_datetime(payload.get("eventTime") or raw.get("EventTime"))
    event_name = payload.get("eventName") or raw.get("EventName")
    if not event_time or not event_name:
        return None
    identity = payload.get("userIdentity") or {}
    if not isinstance(identity, dict):
        identity = {}
    session_context = identity.get("sessionContext") or {}
    if not isinstance(session_context, dict):
        session_context = {}
    session_issuer = session_context.get("sessionIssuer") or {}
    if not isinstance(session_issuer, dict):
        session_issuer = {}
    resources = payload.get("resources") or []
    resource_arns: list[str] = []
    resource_names: list[str] = []
    if isinstance(resources, list):
        for resource in resources:
            if not isinstance(resource, dict):
                continue
            arn = resource.get("ARN") or resource.get("arn")
            name = resource.get("ResourceName") or resource.get("resourceName")
            if arn:
                resource_arns.append(str(arn))
            if name:
                resource_names.append(str(name))
    request = payload.get("requestParameters") or {}
    if isinstance(request, dict):
        for key in ("functionName", "FunctionName", "resource"):
            value = request.get(key)
            if isinstance(value, str):
                if value.startswith("arn:aws:lambda:"):
                    resource_arns.append(value)
                resource_names.append(value.split(":")[-1] if ":" in value else value)
    response = payload.get("responseElements") or {}
    if isinstance(response, dict):
        for key in ("functionArn", "FunctionArn"):
            value = response.get(key)
            if isinstance(value, str):
                resource_arns.append(value)
    return {
        "event_id": raw.get("EventId") or payload.get("eventID") or "",
        "event_time": event_time,
        "event_source": str(payload.get("eventSource") or raw.get("EventSource") or ""),
        "event_name": str(event_name),
        "region": payload.get("awsRegion") or raw.get("AwsRegion"),
        "account_id": payload.get("recipientAccountId") or identity.get("accountId"),
        "principal_type": principal_type_from_identity(identity),
        "principal_arn": identity.get("arn") or identity.get("principalId"),
        "principal_id": identity.get("principalId"),
        "session_issuer_arn": session_issuer.get("arn"),
        "source_identity": session_context.get("sourceIdentity") or identity.get("sourceIdentity"),
        "user_agent": payload.get("userAgent"),
        "resource_arns": sorted(set(resource_arns)),
        "resource_names": sorted(set(resource_names)),
        "request_id": payload.get("requestID"),
        "read_only": payload.get("readOnly"),
        "management_event": payload.get("managementEvent", True),
    }


def match_cloudtrail_event(event: dict[str, Any], *, function_name: str, resource_arn: str | None) -> MatchType | None:
    if resource_arn and resource_arn in event.get("resource_arns", []):
        return MatchType.EXACT_EVENT_RESOURCE
    if function_name in event.get("resource_names", []):
        return MatchType.EXACT_NAME_CONTEXT
    for arn in event.get("resource_arns", []):
        if arn.startswith("arn:aws:lambda:") and arn.split(":")[-1] == function_name:
            return MatchType.EXACT_EVENT_RESOURCE
    return None


class CloudTrailConnector(BaseConnector):
    name = "cloudtrail"
    source = "cloudtrail"

    def __init__(self, settings: Settings, client: Any | None = None, region: str | None = None) -> None:
        super().__init__(settings)
        self.region = region or settings.aws_region
        self._client_instance = client
        self._rate_limiter = RateLimiter(0.6)

    def _client(self) -> Any:
        if self._client_instance is None:
            profile = self.settings.aws_profile or None
            session = boto3.Session(profile_name=profile, region_name=self.region)
            self._client_instance = session.client("cloudtrail", region_name=self.region)
        return self._client_instance

    def is_configured(self) -> bool:
        return bool(self.region)

    def test_connection(self) -> ConnectionTest:
        try:
            self._client().lookup_events(MaxResults=1)
            return ConnectionTest(
                name="CloudTrail",
                status=ConnectorStatus.SUCCESS,
                message="Connected to regional CloudTrail Event History.",
                details={"region": self.region, "event_history_window_days": 90},
            )
        except (ClientError, BotoCoreError, NoCredentialsError, ProfileNotFound) as exc:
            status = _aws_status(exc)
            return ConnectionTest(
                name="CloudTrail",
                status=status,
                message="CloudTrail Event History is not accessible with the current credentials.",
                details={
                    "region": self.region,
                    "error": safe_error_message(exc),
                    "error_class": exc.__class__.__name__,
                },
            )

    def lookup_management_events(
        self,
        *,
        function_name: str,
        resource_arn: str | None = None,
        lookback_days: int | None = None,
    ) -> ConnectorResult:
        if not self.is_configured():
            return self.not_configured("AWS region is not configured for CloudTrail.")
        days = max(1, min(lookback_days or self.settings.cloudtrail_lookback_days, 90))
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)
        events: list[dict[str, Any]] = []
        warnings: list[str] = []
        pages = 0
        next_token: str | None = None
        try:
            while pages < self.settings.max_pages:
                self._rate_limiter.wait()
                kwargs: dict[str, Any] = {
                    "LookupAttributes": [{"AttributeKey": "ResourceName", "AttributeValue": function_name}],
                    "StartTime": start_time,
                    "EndTime": end_time,
                    "MaxResults": 50,
                }
                if next_token:
                    kwargs["NextToken"] = next_token
                response = self._client().lookup_events(**kwargs)
                pages += 1
                for raw in response.get("Events", []):
                    parsed = parse_cloudtrail_event(raw)
                    if not parsed:
                        warnings.append("One CloudTrail event was malformed and could not be parsed.")
                        continue
                    match_type = match_cloudtrail_event(parsed, function_name=function_name, resource_arn=resource_arn)
                    if not match_type:
                        continue
                    parsed["match_type"] = match_type
                    events.append(parsed)
                next_token = response.get("NextToken")
                if not next_token:
                    break
            if next_token:
                warnings.append(
                    f"CloudTrail pagination capped at {self.settings.max_pages} pages; results may be incomplete."
                )
            events.sort(key=lambda item: item["event_time"], reverse=True)
            status = (
                ConnectorStatus.PARTIAL if warnings and "malformed" in " ".join(warnings) else ConnectorStatus.SUCCESS
            )
            return self.result(
                status,
                data=events,
                coverage={
                    "region": self.region,
                    "window_start": start_time,
                    "window_end": end_time,
                    "window_days": days,
                    "event_history_limited": True,
                    "lookup_attribute": "ResourceName",
                },
                warnings=warnings,
                pages=pages,
                records=len(events),
            )
        except Exception as exc:
            status = _aws_status(exc)
            if events:
                status = ConnectorStatus.PARTIAL
            return self.result(
                status,
                data=events,
                coverage={
                    "region": self.region,
                    "window_start": start_time,
                    "window_end": end_time,
                    "window_days": days,
                    "event_history_limited": True,
                },
                warnings=warnings
                + [
                    "CloudTrail Event History is a regional 90-day management-event source, not a last-used or invocation log."
                ],
                error=safe_error_message(exc),
                pages=pages,
                records=len(events),
            )
