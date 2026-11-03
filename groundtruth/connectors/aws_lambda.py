from __future__ import annotations

from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError, ProfileNotFound

from groundtruth.config import Settings
from groundtruth.connectors.base import BaseConnector, safe_error_message
from groundtruth.models.connector import ConnectionTest, ConnectorResult
from groundtruth.models.enums import ConnectorStatus


def _aws_status(exc: BaseException) -> ConnectorStatus:
    if isinstance(exc, (NoCredentialsError, ProfileNotFound)):
        return ConnectorStatus.NOT_CONFIGURED
    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation", "ForbiddenException"}:
            return ConnectorStatus.PERMISSION_DENIED
        if code in {"ResourceNotFoundException", "ResourceNotFound"}:
            return ConnectorStatus.NOT_FOUND
        if code in {"Throttling", "ThrottlingException", "TooManyRequestsException", "RequestLimitExceeded"}:
            return ConnectorStatus.RATE_LIMITED
        if code in {"ExpiredToken", "ExpiredTokenException", "InvalidClientTokenId", "UnrecognizedClientException"}:
            return ConnectorStatus.NOT_CONFIGURED
    return ConnectorStatus.FAILED


def _sanitize_configuration(config: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    blocked = {"Environment", "Code", "Variables"}
    for key, value in config.items():
        if key in blocked:
            continue
        if key == "Description" and value:
            safe[key] = str(value)[:300]
        else:
            safe[key] = value
    return safe


class AwsLambdaConnector(BaseConnector):
    name = "aws_lambda"
    source = "aws_lambda"

    def __init__(self, settings: Settings, session: Any | None = None, region: str | None = None) -> None:
        super().__init__(settings)
        self.region = region or settings.aws_region
        self._session = session
        self._lambda: Any | None = None
        self._iam: Any | None = None
        self._sts: Any | None = None

    def _build_session(self) -> Any:
        if self._session is not None:
            return self._session
        profile = self.settings.aws_profile or None
        self._session = boto3.Session(profile_name=profile, region_name=self.region)
        return self._session

    def _client(self, service: str) -> Any:
        if service == "lambda":
            if self._lambda is None:
                self._lambda = self._build_session().client("lambda", region_name=self.region)
            return self._lambda
        if service == "iam":
            if self._iam is None:
                self._iam = self._build_session().client("iam")
            return self._iam
        if service == "sts":
            if self._sts is None:
                self._sts = self._build_session().client("sts")
            return self._sts
        raise ValueError("unsupported AWS service")

    def is_configured(self) -> bool:
        return bool(self.region)

    def test_connection(self) -> ConnectionTest:
        try:
            identity = self._client("sts").get_caller_identity()
            self._client("lambda").list_functions(MaxItems=1)
            return ConnectionTest(
                name="AWS",
                status=ConnectorStatus.SUCCESS,
                message="Connected with read-only AWS credentials.",
                details={
                    "account_id": identity.get("Account"),
                    "caller_arn": identity.get("Arn"),
                    "region": self.region,
                },
            )
        except (ClientError, BotoCoreError, NoCredentialsError, ProfileNotFound) as exc:
            status = _aws_status(exc)
            messages = {
                ConnectorStatus.NOT_CONFIGURED: "AWS credentials or profile are not configured. Run aws sso login or set AWS_PROFILE.",
                ConnectorStatus.PERMISSION_DENIED: "AWS credentials are connected but Lambda list permission is missing.",
                ConnectorStatus.RATE_LIMITED: "AWS rate-limited the connection test. Retry shortly.",
                ConnectorStatus.FAILED: "AWS connection test failed.",
            }
            return ConnectionTest(
                name="AWS",
                status=status,
                message=messages.get(status, "AWS connection test failed."),
                details={
                    "error": safe_error_message(exc),
                    "region": self.region,
                    "error_class": exc.__class__.__name__,
                },
            )

    def get_caller_identity(self) -> ConnectorResult:
        try:
            identity = self._client("sts").get_caller_identity()
            return self.result(
                ConnectorStatus.SUCCESS,
                data={
                    "account_id": identity.get("Account"),
                    "caller_arn": identity.get("Arn"),
                    "user_id": identity.get("UserId"),
                    "region": self.region,
                },
                coverage={"account_id": identity.get("Account"), "region": self.region},
                records=1,
            )
        except Exception as exc:
            return self.result(_aws_status(exc), error=safe_error_message(exc), coverage={"region": self.region})

    def list_functions(self) -> ConnectorResult:
        if not self.is_configured():
            return self.not_configured("AWS region is not configured.")
        try:
            paginator = self._client("lambda").get_paginator("list_functions")
            items: list[dict[str, Any]] = []
            pages = 0
            for page in paginator.paginate(PaginationConfig={"MaxItems": self.settings.max_pages * 50, "PageSize": 50}):
                pages += 1
                for item in page.get("Functions", []):
                    items.append(_sanitize_configuration(item))
                if pages >= self.settings.max_pages:
                    break
            warnings = []
            if pages >= self.settings.max_pages:
                warnings.append(f"Pagination capped at {self.settings.max_pages} pages; inventory may be incomplete.")
            return self.result(
                ConnectorStatus.SUCCESS,
                data=items,
                coverage={"region": self.region, "pagination_capped": pages >= self.settings.max_pages},
                warnings=warnings,
                pages=pages,
                records=len(items),
            )
        except Exception as exc:
            return self.result(_aws_status(exc), error=safe_error_message(exc), coverage={"region": self.region})

    def _optional(self, callable_: Any, label: str) -> tuple[Any | None, str | None]:
        try:
            return callable_(), None
        except ClientError as exc:
            return None, f"{label} unavailable: {safe_error_message(exc)}"
        except BotoCoreError as exc:
            return None, f"{label} unavailable: {safe_error_message(exc)}"

    def get_function(self, function_name: str) -> ConnectorResult:
        if not self.is_configured():
            return self.not_configured("AWS region is not configured.")
        try:
            response = self._client("lambda").get_function(FunctionName=function_name)
        except Exception as exc:
            return self.result(_aws_status(exc), error=safe_error_message(exc), coverage={"region": self.region})
        configuration = _sanitize_configuration(response.get("Configuration", {}))
        configuration.pop("Code", None)
        arn = configuration.get("FunctionArn") or function_name
        tags, tags_warning = self._optional(lambda: self._client("lambda").list_tags(Resource=arn), "Lambda tags")
        mappings, mappings_warning = self._optional(
            lambda: self._client("lambda").list_event_source_mappings(FunctionName=arn), "Event source mappings"
        )
        aliases, aliases_warning = self._optional(
            lambda: self._client("lambda").list_aliases(
                FunctionName=configuration.get("FunctionName") or function_name
            ),
            "Aliases",
        )
        url_config, url_warning = self._optional(
            lambda: self._client("lambda").get_function_url_config(
                FunctionName=configuration.get("FunctionName") or function_name
            ),
            "Function URL configuration",
        )
        invoke_config, invoke_warning = self._optional(
            lambda: self._client("lambda").get_function_event_invoke_config(
                FunctionName=configuration.get("FunctionName") or function_name
            ),
            "Event invoke configuration",
        )
        role_info = None
        role_warning = None
        role_arn = configuration.get("Role")
        if role_arn and str(role_arn).startswith("arn:") and ":role/" in str(role_arn):
            role_name = str(role_arn).split(":role/", 1)[1].split("/")[-1]
            role_info, role_warning = self._optional(
                lambda: self._client("iam").get_role(RoleName=role_name), "IAM role metadata"
            )
        warnings = [
            warning
            for warning in (
                tags_warning,
                mappings_warning,
                aliases_warning,
                url_warning,
                invoke_warning,
                role_warning,
            )
            if warning
        ]
        status = ConnectorStatus.PARTIAL if warnings else ConnectorStatus.SUCCESS
        return self.result(
            status,
            data={
                "function": configuration,
                "tags": (tags or {}).get("Tags", {}),
                "event_source_mappings": (mappings or {}).get("EventSourceMappings", []),
                "aliases": (aliases or {}).get("Aliases", []),
                "function_url": url_config,
                "event_invoke_config": invoke_config,
                "role": role_info.get("Role") if role_info else None,
            },
            coverage={
                "region": self.region,
                "account_id": (configuration.get("FunctionArn") or "").split(":")[4]
                if (configuration.get("FunctionArn") or "").count(":") >= 6
                else None,
            },
            warnings=warnings,
            records=1,
        )
