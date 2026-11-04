from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from groundtruth.ai.prompt_builder import redact_arn
from groundtruth.ai.tool_schema import SchemaValidationError, validate_json_schema
from groundtruth.mcp.manager import McpManager
from groundtruth.mcp.tool_registry import SHELL_TERMS, WRITE_VERBS
from groundtruth.models.enums import SourceType
from groundtruth.models.lineage import LineageResult
from groundtruth.utils.redaction import redact_account_id, safe_text, strip_sensitive_url_parts

MAX_ARGUMENT_CHARS = 8000
MAX_RESULT_CHARS = 6000
MAX_MCP_RESULT_CHARS = 3000


class ToolError(RuntimeError):
    pass


class ToolPermissionError(ToolError):
    pass


class ToolArgumentError(ToolError):
    pass


class ToolExecutionError(ToolError):
    pass


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _LookupResourceLineageArgs(_StrictModel):
    resource_arn: str | None = Field(default=None, max_length=2048)
    function_name: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _require_scope(self) -> "_LookupResourceLineageArgs":
        if not self.resource_arn and not self.function_name:
            raise ValueError("provide resource_arn or function_name")
        return self


class _GetWorkspaceRunsArgs(_StrictModel):
    workspace_id: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=5, ge=1, le=10)


class _InspectGitCommitArgs(_StrictModel):
    sha: str | None = Field(default=None, max_length=40)


class _GetCloudTrailEventsArgs(_StrictModel):
    event_name: str | None = Field(default=None, max_length=120)
    limit: int = Field(default=10, ge=1, le=20)


class _GetCloudWatchMetricsArgs(_StrictModel):
    metric: str = Field(default="Invocations", pattern="^(Invocations|Errors|Throttles|Duration)$")


@dataclass
class ToolCallRecord:
    tool: str
    arguments: dict[str, Any]
    started_at: datetime
    duration_ms: int = 0
    status: str = "running"
    evidence_ids: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class ToolSpec:
    name: str
    description: str
    schema: dict[str, Any]
    handler: Callable[[Any], dict[str, Any]]
    args_model: type[BaseModel] | None = None
    read_only: bool = True
    citable: bool = True

    def definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": safe_text(self.description, limit=800),
                "parameters": self.schema,
            },
        }


def _evidence_ids(result: LineageResult, *sources: SourceType) -> list[str]:
    wanted = set(sources)
    return [item.evidence_id for item in result.evidence if item.source in wanted]


def _duration_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


def _safe(value: Any, limit: int = 500) -> str:
    return safe_text(strip_sensitive_url_parts(str(value or "")), limit=limit)


def _forbidden_tool_name(name: str) -> bool:
    return bool(SHELL_TERMS.search(name) or WRITE_VERBS.search(name))


class InternalToolRegistry:
    """Read-only tools exposed to the Muse Spark tool-calling loop.

    The direct tools read from the deterministic investigation result that was
    just produced by the existing connectors. They never issue a new cloud API
    call and are scoped to the current investigation so the model cannot use
    GroundTruth as a general-purpose cloud reader.
    """

    def __init__(
        self,
        result: LineageResult,
        *,
        mcp_manager: McpManager | None = None,
        max_result_chars: int = MAX_RESULT_CHARS,
    ) -> None:
        self.result = result
        self.mcp_manager = mcp_manager
        self.max_result_chars = max(1000, min(int(max_result_chars), MAX_RESULT_CHARS))
        self.calls: list[ToolCallRecord] = []
        self._tools: dict[str, ToolSpec] = {}
        self._register_direct_tools()
        if mcp_manager is not None and mcp_manager.enabled:
            self._register_mcp_tools(mcp_manager)

    @property
    def tools(self) -> list[ToolSpec]:
        return sorted(self._tools.values(), key=lambda item: item.name)

    def definitions(self) -> list[dict[str, Any]]:
        return [item.definition() for item in self.tools]

    def allowed_names(self) -> set[str]:
        return set(self._tools)

    def _add(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ToolExecutionError(f"Duplicate tool name: {spec.name}.")
        self._tools[spec.name] = spec

    def _register_direct_tools(self) -> None:
        self._add(
            ToolSpec(
                name="lookup_resource_lineage",
                description=(
                    "Read the current investigation's deterministic lineage summary. Use it to confirm the "
                    "resource identity, status, confidence, owners, coverage gaps, and citable evidence IDs. "
                    "It only works for the resource already under investigation; it does not query other resources."
                ),
                schema=_schema(_LookupResourceLineageArgs),
                args_model=_LookupResourceLineageArgs,
                handler=self._lookup_resource_lineage,
            )
        )
        self._add(
            ToolSpec(
                name="get_workspace_runs",
                description=(
                    "Read workspace, run, and state-version evidence already collected for this investigation. "
                    "Optional workspace_id narrows the result. Returns evidence IDs for citation."
                ),
                schema=_schema(_GetWorkspaceRunsArgs),
                args_model=_GetWorkspaceRunsArgs,
                handler=self._get_workspace_runs,
            )
        )
        self._add(
            ToolSpec(
                name="inspect_git_commit",
                description=(
                    "Read the repository lineage and exact-commit evidence already collected for this "
                    "investigation. Optional sha must match the collected commit. Returns commit metadata, "
                    "verified status, file matches, and evidence IDs."
                ),
                schema=_schema(_InspectGitCommitArgs),
                args_model=_InspectGitCommitArgs,
                handler=self._inspect_git_commit,
            )
        )
        self._add(
            ToolSpec(
                name="get_cloudtrail_events",
                description=(
                    "Read matching CloudTrail management events already collected for this investigation. "
                    "These are management events, not invocation history, and are limited to the configured "
                    "regional retention window. Optional event_name filters the result."
                ),
                schema=_schema(_GetCloudTrailEventsArgs),
                args_model=_GetCloudTrailEventsArgs,
                handler=self._get_cloudtrail_events,
            )
        )
        self._add(
            ToolSpec(
                name="get_cloudwatch_metrics",
                description=(
                    "Read the CloudWatch Lambda activity summary already collected for this investigation. "
                    "A missing datapoint is not proof that the function is unused."
                ),
                schema=_schema(_GetCloudWatchMetricsArgs),
                args_model=_GetCloudWatchMetricsArgs,
                handler=self._get_cloudwatch_metrics,
            )
        )

    def _register_mcp_tools(self, manager: McpManager) -> None:
        for tool in manager.registry.approved_tools():
            if not tool.read_only or not tool.enabled:
                continue
            safe_server = re.sub(r"[^A-Za-z0-9_]", "_", tool.server)[:32]
            safe_tool = re.sub(r"[^A-Za-z0-9_]", "_", tool.name)[:48]
            qualified = f"mcp__{safe_server}__{safe_tool}"
            if qualified in self._tools:
                qualified = f"{qualified}_{len(self._tools)}"
            schema = tool.input_schema if isinstance(tool.input_schema, dict) else {}
            if schema.get("type") != "object":
                schema = {"type": "object", "additionalProperties": True}
            self._add(
                ToolSpec(
                    name=qualified,
                    description=(
                        f"Read-only MCP tool from server {tool.server!r}: {tool.description or tool.name}. "
                        "The tool must remain allowlisted and read-classified at execution time. Its output is "
                        "supplemental context and is not a citable GroundTruth evidence ID."
                    ),
                    schema=schema,
                    handler=self._mcp_handler(tool.server, tool.name),
                    args_model=None,
                    citable=False,
                )
            )

    def _mcp_handler(self, server: str, tool_name: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
        def handler(arguments: dict[str, Any]) -> dict[str, Any]:
            manager = self.mcp_manager
            if manager is None:
                raise ToolPermissionError("MCP is not configured.")
            # Re-check policy immediately before execution. Discovery-time
            # approval is not authorization.
            manager.registry.authorize(server, tool_name)
            result = manager.call(f"{server}:{tool_name}", arguments)
            text = _safe(result.text, limit=MAX_MCP_RESULT_CHARS)
            return {
                "source": "mcp",
                "server": _safe(server, limit=80),
                "tool": _safe(tool_name, limit=120),
                "is_error": bool(result.is_error),
                "content": text or "[no text content returned]",
                "evidence_ids": [],
                "note": "Supplemental MCP context; not a citable GroundTruth evidence record.",
            }

        return handler

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        spec = self._tools.get(name)
        started_at = datetime.now(timezone.utc)
        started = time.monotonic()
        record = ToolCallRecord(tool=name, arguments=_redact_args(arguments), started_at=started_at)
        self.calls.append(record)
        if spec is None:
            if _forbidden_tool_name(name):
                record.status = "refused"
                record.error = "write/execute tool names are not permitted"
                raise ToolPermissionError("The model requested a write or execute tool that is not exposed.")
            record.status = "refused"
            record.error = "unknown tool"
            raise ToolPermissionError("The model requested a tool that is not registered for this investigation.")
        if not spec.read_only:
            record.status = "refused"
            record.error = "not read-only"
            raise ToolPermissionError("The requested tool is not read-only.")
        serialized = json.dumps(arguments or {}, ensure_ascii=True, sort_keys=True)
        if len(serialized) > MAX_ARGUMENT_CHARS:
            record.status = "rejected"
            record.error = "arguments too large"
            raise ToolArgumentError("Tool arguments exceed the configured input cap.")
        try:
            if spec.args_model is not None:
                validated = spec.args_model.model_validate(arguments or {})
                call_args: Any = validated
            else:
                validate_json_schema(arguments or {}, spec.schema)
                call_args = arguments or {}
        except (ValidationError, SchemaValidationError) as exc:
            record.status = "rejected"
            record.error = safe_text(str(exc), limit=300)
            raise ToolArgumentError(f"Tool arguments failed schema validation: {record.error}") from exc
        try:
            payload = spec.handler(call_args)
        except ToolPermissionError:
            record.status = "refused"
            record.duration_ms = _duration_ms(started)
            record.error = "permission denied"
            raise
        except ToolArgumentError as exc:
            record.status = "rejected"
            record.duration_ms = _duration_ms(started)
            record.error = safe_text(str(exc), limit=300)
            raise
        except Exception as exc:
            record.status = "error"
            record.duration_ms = _duration_ms(started)
            record.error = safe_text(f"{exc.__class__.__name__}: {exc}", limit=300)
            raise ToolExecutionError(record.error) from exc
        evidence_ids = payload.get("evidence_ids") if isinstance(payload.get("evidence_ids"), list) else []
        record.evidence_ids = [str(item) for item in evidence_ids[:40] if isinstance(item, str)]
        fitted = _fit_result(payload, self.max_result_chars, record.evidence_ids)
        record.status = "ok"
        record.duration_ms = _duration_ms(started)
        return fitted

    def _lookup_resource_lineage(self, args: _LookupResourceLineageArgs) -> dict[str, Any]:
        result = self.result
        if args.resource_arn:
            requested = args.resource_arn.strip()
            if result.resource.arn and requested != result.resource.arn:
                raise ToolArgumentError(
                    "This tool is scoped to the current investigation. Start a new investigation for another ARN."
                )
            if not result.resource.arn and requested.rsplit(":", 1)[-1] != result.resource.name:
                raise ToolArgumentError("The requested ARN does not match the current investigation.")
        if args.function_name and args.function_name.strip() != result.resource.name:
            raise ToolArgumentError(
                "This tool is scoped to the current investigation. Start a new investigation for another function."
            )
        owners = [
            {
                "kind": owner.kind,
                "workspace_id": owner.workspace.id,
                "workspace_name": owner.workspace.name,
                "resource_address": owner.resource_address,
                "match_type": owner.match_type.value,
                "last_seen_at": owner.last_seen_at.isoformat() if owner.last_seen_at else None,
                "evidence_ids": owner.evidence_ids[:8],
            }
            for owner in result.current_owners + result.historical_managers
        ]
        gaps = [
            {
                "source": item.source,
                "status": item.status.value,
                "required": item.required,
                "records": item.records,
                "error": _safe(item.error, limit=300) if item.error else None,
            }
            for item in result.coverage_gaps()
        ]
        evidence_ids = _evidence_ids(result, SourceType.AWS_LAMBDA)
        evidence_ids += [
            item for owner in result.current_owners + result.historical_managers for item in owner.evidence_ids
        ]
        return {
            "scope": "current_investigation",
            "fixture": result.fixture,
            "resource": {
                "name": result.resource.name,
                "arn": redact_arn(result.resource.arn),
                "account_id": redact_account_id(result.resource.account_id),
                "region": result.resource.region,
            },
            "deterministic_result": {
                "status": result.status.value,
                "confidence": result.confidence.value,
                "status_reason": _safe(result.status_reason, limit=600),
                "confidence_rule": _safe(result.confidence_rule, limit=400),
                "recommendation_code": result.recommendation.code.value,
                "blocked_adoption": result.recommendation.blocked_adoption,
            },
            "owners": owners[:20],
            "coverage_gaps": gaps[:20],
            "evidence_ids": _dedupe(evidence_ids),
        }

    def _get_workspace_runs(self, args: _GetWorkspaceRunsArgs) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        evidence_ids: list[str] = []
        for owner in self.result.current_owners + self.result.historical_managers:
            if args.workspace_id and owner.workspace.id != args.workspace_id:
                continue
            run = owner.run
            state = owner.state_version
            records.append(
                {
                    "workspace_id": owner.workspace.id,
                    "workspace_name": owner.workspace.name,
                    "workspace_active": owner.workspace.active,
                    "resource_address": owner.resource_address,
                    "ownership_kind": owner.kind,
                    "match_type": owner.match_type.value,
                    "run": {
                        "id": run.id,
                        "status": run.status,
                        "created_at": run.created_at.isoformat() if run and run.created_at else None,
                        "actor": _safe(run.actor, limit=160) if run and run.actor else None,
                        "vcs_revision": run.vcs_revision,
                    }
                    if run
                    else None,
                    "state_version_id": state.id if state else None,
                    "evidence_ids": owner.evidence_ids[:8],
                }
            )
            evidence_ids.extend(owner.evidence_ids)
            if len(records) >= args.limit:
                break
        return {
            "workspace_filter": args.workspace_id,
            "records": records,
            "evidence_ids": _dedupe(evidence_ids),
            "note": "No workspace record matched the requested ID." if args.workspace_id and not records else None,
        }

    def _inspect_git_commit(self, args: _InspectGitCommitArgs) -> dict[str, Any]:
        lineage = self.result.repository_lineage
        if lineage is None:
            return {
                "available": False,
                "note": "No repository lineage was collected for this investigation.",
                "evidence_ids": [],
            }
        sha = lineage.vcs_revision or (lineage.commit.sha if lineage.commit else None)
        if args.sha:
            requested = args.sha.strip().lower()
            candidates = {
                value.lower()
                for value in (lineage.vcs_revision, lineage.commit.sha if lineage.commit else None)
                if value
            }
            if not any(candidate.startswith(requested) or requested.startswith(candidate) for candidate in candidates):
                raise ToolArgumentError("The requested SHA does not match the commit collected for this investigation.")
            sha = requested
        commit = lineage.commit
        files = [
            {
                "path": _safe(item.path, limit=300),
                "line": item.line,
                "matched_string": _safe(item.matched_string, limit=160),
                "match_type": item.match_type.value,
            }
            for item in (lineage.file_matches + lineage.history_matches)[:20]
        ]
        evidence_ids = _evidence_ids(self.result, SourceType.GIT_COMMIT, SourceType.GIT_FILE)
        return {
            "available": True,
            "repository": _safe(lineage.repository, limit=200),
            "working_directory": _safe(lineage.working_directory, limit=200) if lineage.working_directory else None,
            "branch": _safe(lineage.branch, limit=120) if lineage.branch else None,
            "vcs_revision": sha,
            "commit_verified": lineage.commit_verified,
            "candidate_only": lineage.candidate_only,
            "commit": {
                "sha": commit.sha if commit else None,
                "author_name": _safe(commit.author_name, limit=120) if commit and commit.author_name else None,
                "committed_at": commit.committed_at.isoformat() if commit and commit.committed_at else None,
                "message": _safe(commit.message, limit=300) if commit else None,
            }
            if commit
            else None,
            "files": files,
            "limitations": [_safe(item, limit=300) for item in lineage.limitations[:6]],
            "evidence_ids": evidence_ids,
        }

    def _get_cloudtrail_events(self, args: _GetCloudTrailEventsArgs) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        evidence_ids: list[str] = []
        for event in self.result.cloudtrail_events:
            if args.event_name and event.event_name != args.event_name:
                continue
            evidence_id = next(
                (item.evidence_id for item in self.result.evidence if item.source_record_id == event.event_id),
                None,
            )
            if evidence_id:
                evidence_ids.append(evidence_id)
            events.append(
                {
                    "event_name": event.event_name,
                    "event_time": event.event_time.isoformat(),
                    "event_source": event.event_source,
                    "principal_type": event.principal_type.value,
                    "principal_arn": redact_arn(event.principal_arn),
                    "source_identity": _safe(event.source_identity, limit=160) if event.source_identity else None,
                    "match_type": event.match_type.value,
                    "evidence_id": evidence_id,
                }
            )
            if len(events) >= args.limit:
                break
        return {
            "events": events,
            "event_name_filter": args.event_name,
            "evidence_ids": _dedupe(evidence_ids),
            "note": (
                "CloudTrail management events are not invocation history. Event History is regional and limited "
                "to the configured lookback window (at most 90 days)."
            ),
        }

    def _get_cloudwatch_metrics(self, args: _GetCloudWatchMetricsArgs) -> dict[str, Any]:
        activity = self.result.activity
        evidence_ids = _evidence_ids(self.result, SourceType.CLOUDWATCH_METRIC)
        if activity is None:
            return {
                "available": False,
                "metric": args.metric,
                "note": "No CloudWatch activity summary was collected for this investigation.",
                "evidence_ids": evidence_ids,
            }
        metric_values: dict[str, Any]
        if args.metric == "Invocations":
            metric_values = {
                "total": activity.total_invocations,
                "datapoints": activity.invocation_datapoints,
                "latest_nonzero_at": activity.latest_nonzero_invocations_at.isoformat()
                if activity.latest_nonzero_invocations_at
                else None,
                "latest_nonzero_sum": activity.latest_nonzero_invocation_sum,
            }
        elif args.metric == "Errors":
            metric_values = {"total": activity.total_errors, "datapoints": activity.error_datapoints}
        elif args.metric == "Throttles":
            metric_values = {"total": activity.total_throttles, "datapoints": activity.throttle_datapoints}
        else:
            metric_values = {
                "average_duration_ms": activity.average_duration_ms,
                "maximum_duration_ms": activity.maximum_duration_ms,
            }
        return {
            "available": True,
            "metric": args.metric,
            "window_start": activity.window_start.isoformat(),
            "window_end": activity.window_end.isoformat(),
            "period_seconds": activity.period_seconds,
            "no_datapoints": activity.no_datapoints,
            "values": metric_values,
            "evidence_ids": evidence_ids,
            "note": "Metric buckets are aggregate intervals. No datapoint returned does not prove the function is unused.",
        }


def _schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    schema["additionalProperties"] = False
    schema.pop("title", None)
    return schema


def _redact_args(value: Any, key: str | None = None) -> Any:
    if key and re.search(r"(?i)(secret|token|password|credential|authorization)", key):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(item_key): _redact_args(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact_args(item, key) for item in value]
    if isinstance(value, str):
        return _safe(value, limit=500)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _safe(value, limit=500)


def _fit_result(payload: dict[str, Any], limit: int, evidence_ids: list[str]) -> dict[str, Any]:
    serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    if len(serialized) <= limit:
        return payload
    return {
        "truncated": True,
        "note": "The tool result exceeded the configured result cap and was replaced with a compact summary.",
        "evidence_ids": evidence_ids[:40],
        "keys": sorted(str(key) for key in payload)[:20],
    }


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
