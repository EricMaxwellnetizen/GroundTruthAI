from __future__ import annotations

from enum import Enum


class SourceType(str, Enum):
    AWS_LAMBDA = "aws_lambda"
    SCALR_RESOURCE_USAGE = "scalr_resource_usage"
    SCALR_STATE = "scalr_state"
    SCALR_WORKSPACE = "scalr_workspace"
    SCALR_RUN = "scalr_run"
    GIT_COMMIT = "git_commit"
    GIT_FILE = "git_file"
    CLOUDTRAIL = "cloudtrail"
    CLOUDWATCH_METRIC = "cloudwatch_metric"
    CLOUDWATCH_OMNI = "cloudwatch_omni"
    FIXTURE = "fixture"
    MANUAL = "manual"


class MatchType(str, Enum):
    EXACT_ARN = "exact_arn"
    EXACT_PROVIDER_ID = "exact_provider_id"
    EXACT_ADDRESS = "exact_address"
    WORKSPACE_RELATION = "workspace_relation"
    EXACT_COMMIT_SHA = "exact_commit_sha"
    EXACT_EVENT_RESOURCE = "exact_event_resource"
    EXACT_NAME_CONTEXT = "exact_name_context"
    CANDIDATE_NAME = "candidate_name"
    INFERRED_DEPENDENCY = "inferred_dependency"
    MANUAL_ATTACHMENT = "manual_attachment"


class LineageStatus(str, Enum):
    CURRENT_OWNER_FOUND = "CURRENT_OWNER_FOUND"
    HISTORICAL_OWNER_FOUND = "HISTORICAL_OWNER_FOUND"
    MULTIPLE_ACTIVE_OWNERS = "MULTIPLE_ACTIVE_OWNERS"
    CANDIDATE_LINEAGE = "CANDIDATE_LINEAGE"
    UNATTRIBUTED_IN_CHECKED_SOURCES = "UNATTRIBUTED_IN_CHECKED_SOURCES"
    INSUFFICIENT_ACCESS = "INSUFFICIENT_ACCESS"
    IDENTITY_AMBIGUOUS = "IDENTITY_AMBIGUOUS"


class ConfidenceLabel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class ConnectorStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    NOT_CONFIGURED = "not_configured"
    PERMISSION_DENIED = "permission_denied"
    RATE_LIMITED = "rate_limited"
    NOT_FOUND = "not_found"
    FAILED = "failed"


class Sensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"


class PrincipalType(str, Enum):
    IAM_USER = "iam_user"
    ASSUMED_ROLE = "assumed_role"
    AWS_SERVICE = "aws_service"
    ROOT = "root"
    FEDERATED_USER = "federated_user"
    UNKNOWN = "unknown"


class ActivityMetric(str, Enum):
    INVOCATIONS = "Invocations"
    ERRORS = "Errors"
    THROTTLES = "Throttles"
    DURATION = "Duration"


class RecommendationCode(str, Enum):
    INSPECT_CURRENT_WORKSPACE = "INSPECT_CURRENT_WORKSPACE"
    INSPECT_LAST_KNOWN_STATE_AND_RUN = "INSPECT_LAST_KNOWN_STATE_AND_RUN"
    RESOLVE_DUPLICATE_STATE_OWNERSHIP = "RESOLVE_DUPLICATE_STATE_OWNERSHIP"
    VERIFY_GIT_REPOSITORY_AND_WORKING_DIRECTORY = "VERIFY_GIT_REPOSITORY_AND_WORKING_DIRECTORY"
    CHECK_CLOUDTRAIL_RETENTION_OR_TRAIL = "CHECK_CLOUDTRAIL_RETENTION_OR_TRAIL"
    CHECK_CLOUDWATCH_ACTIVITY_DATA = "CHECK_CLOUDWATCH_ACTIVITY_DATA"
    REQUEST_MISSING_READ_PERMISSION = "REQUEST_MISSING_READ_PERMISSION"
    REVIEW_CANDIDATE_MATCH_MANUALLY = "REVIEW_CANDIDATE_MATCH_MANUALLY"
    PREPARE_SEPARATE_ADOPTION_PROPOSAL = "PREPARE_SEPARATE_ADOPTION_PROPOSAL"
    SUPPLY_EXACT_RESOURCE_ARN = "SUPPLY_EXACT_RESOURCE_ARN"
