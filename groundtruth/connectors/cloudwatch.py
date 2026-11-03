from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError, ProfileNotFound

from groundtruth.config import Settings
from groundtruth.connectors.aws_lambda import _aws_status
from groundtruth.connectors.base import BaseConnector, safe_error_message
from groundtruth.models.connector import ConnectionTest, ConnectorResult
from groundtruth.models.enums import ConnectorStatus
from groundtruth.models.lineage import CloudWatchActivity


def _series_with_times(result: dict[str, Any]) -> list[tuple[datetime, float]]:
    timestamps = result.get("Timestamps") or []
    values = result.get("Values") or []
    pairs: list[tuple[datetime, float]] = []
    for timestamp, value in zip(timestamps, values, strict=False):
        if isinstance(timestamp, datetime):
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            try:
                pairs.append((timestamp, float(value)))
            except (TypeError, ValueError):
                continue
    pairs.sort(key=lambda item: item[0], reverse=True)
    return pairs


class CloudWatchMetricsConnector(BaseConnector):
    name = "cloudwatch"
    source = "cloudwatch_metric"

    def __init__(self, settings: Settings, client: Any | None = None, region: str | None = None) -> None:
        super().__init__(settings)
        self.region = region or settings.aws_region
        self._client_instance = client

    def _client(self) -> Any:
        if self._client_instance is None:
            profile = self.settings.aws_profile or None
            session = boto3.Session(profile_name=profile, region_name=self.region)
            self._client_instance = session.client("cloudwatch", region_name=self.region)
        return self._client_instance

    def is_configured(self) -> bool:
        return bool(self.region)

    def test_connection(self) -> ConnectionTest:
        try:
            self._client().list_metrics(Namespace="AWS/Lambda")
            return ConnectionTest(
                name="CloudWatch",
                status=ConnectorStatus.SUCCESS,
                message="Connected to CloudWatch metrics.",
                details={"region": self.region, "namespace": "AWS/Lambda"},
            )
        except (ClientError, BotoCoreError, NoCredentialsError, ProfileNotFound) as exc:
            return ConnectionTest(
                name="CloudWatch",
                status=_aws_status(exc),
                message="CloudWatch metrics are not accessible with the current credentials.",
                details={
                    "region": self.region,
                    "error": safe_error_message(exc),
                    "error_class": exc.__class__.__name__,
                },
            )

    def get_activity(self, *, function_name: str, lookback_days: int | None = None) -> ConnectorResult:
        if not self.is_configured():
            return self.not_configured("AWS region is not configured for CloudWatch.")
        days = max(1, lookback_days or self.settings.cloudwatch_lookback_days)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)
        period = self.settings.cloudwatch_period_seconds
        dimensions = [{"Name": "FunctionName", "Value": function_name}]
        queries = [
            {
                "Id": "invocations",
                "MetricStat": {
                    "Metric": {"Namespace": "AWS/Lambda", "MetricName": "Invocations", "Dimensions": dimensions},
                    "Period": period,
                    "Stat": "Sum",
                },
                "ReturnData": True,
            },
            {
                "Id": "errors",
                "MetricStat": {
                    "Metric": {"Namespace": "AWS/Lambda", "MetricName": "Errors", "Dimensions": dimensions},
                    "Period": period,
                    "Stat": "Sum",
                },
                "ReturnData": True,
            },
            {
                "Id": "throttles",
                "MetricStat": {
                    "Metric": {"Namespace": "AWS/Lambda", "MetricName": "Throttles", "Dimensions": dimensions},
                    "Period": period,
                    "Stat": "Sum",
                },
                "ReturnData": True,
            },
            {
                "Id": "duration_avg",
                "MetricStat": {
                    "Metric": {"Namespace": "AWS/Lambda", "MetricName": "Duration", "Dimensions": dimensions},
                    "Period": period,
                    "Stat": "Average",
                },
                "ReturnData": True,
            },
            {
                "Id": "duration_max",
                "MetricStat": {
                    "Metric": {"Namespace": "AWS/Lambda", "MetricName": "Duration", "Dimensions": dimensions},
                    "Period": period,
                    "Stat": "Maximum",
                },
                "ReturnData": True,
            },
        ]
        try:
            response = self._client().get_metric_data(
                MetricDataQueries=queries,
                StartTime=start_time,
                EndTime=end_time,
                ScanBy="TimestampDescending",
            )
        except Exception as exc:
            return self.result(
                _aws_status(exc),
                error=safe_error_message(exc),
                coverage={"region": self.region, "window_start": start_time, "window_end": end_time},
            )
        results = {item.get("Id"): item for item in response.get("MetricDataResults", [])}
        invocations = _series_with_times(results.get("invocations", {}))
        errors = _series_with_times(results.get("errors", {}))
        throttles = _series_with_times(results.get("throttles", {}))
        duration_avg = _series_with_times(results.get("duration_avg", {}))
        duration_max = _series_with_times(results.get("duration_max", {}))
        latest_nonzero = next(((timestamp, value) for timestamp, value in invocations if value > 0), None)
        warnings = []
        messages = response.get("Messages") or []
        for message in messages:
            if isinstance(message, dict):
                text = message.get("Value") or message.get("Code")
                if text:
                    warnings.append(str(text)[:300])
        activity = CloudWatchActivity(
            window_start=start_time,
            window_end=end_time,
            period_seconds=period,
            metric_namespace="AWS/Lambda",
            dimensions={"FunctionName": function_name},
            latest_nonzero_invocations_at=latest_nonzero[0] if latest_nonzero else None,
            latest_nonzero_invocation_sum=latest_nonzero[1] if latest_nonzero else None,
            total_invocations=sum(value for _, value in invocations),
            total_errors=sum(value for _, value in errors),
            total_throttles=sum(value for _, value in throttles),
            average_duration_ms=(sum(value for _, value in duration_avg) / len(duration_avg)) if duration_avg else None,
            maximum_duration_ms=max((value for _, value in duration_max), default=None),
            invocation_datapoints=len(invocations),
            error_datapoints=len(errors),
            throttle_datapoints=len(throttles),
            no_datapoints=not any((invocations, errors, throttles, duration_avg, duration_max)),
            limitations=[
                "Lambda service metrics are emitted in aggregate intervals; a metric bucket is not an exact invocation time.",
                "No datapoint returned for this query does not prove the function is unused.",
            ],
        )
        return self.result(
            ConnectorStatus.SUCCESS,
            data=activity,
            coverage={
                "region": self.region,
                "window_start": start_time,
                "window_end": end_time,
                "period_seconds": period,
                "metric_namespace": "AWS/Lambda",
            },
            warnings=warnings,
            records=activity.invocation_datapoints,
        )
