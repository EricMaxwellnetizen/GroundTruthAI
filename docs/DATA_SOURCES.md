# Data sources

Each source contributes evidence, not certainty. GroundTruth preserves the distinction between a successful empty search, a permission gap, and an unconfigured source.

## AWS Lambda

**API:** `lambda:GetFunction`, `lambda:ListFunctions`, `lambda:ListAliases`, `lambda:ListTags`, `lambda:ListEventSourceMappings`, `lambda:GetFunctionUrlConfig`, `lambda:GetFunctionEventInvokeConfig`; `iam:GetRole` for execution-role metadata; `sts:GetCallerIdentity` for account context.

**Proves:** the function and version exist in the chosen account/region; its ARN, runtime, role, tags, aliases, event source mappings, and related configuration.

**Does not prove:** who owns it, which repository defines it, or who changed it. Environment-variable values and downloadable code packages are excluded from evidence.

## CloudTrail Event History

**API:** `cloudtrail:LookupEvents`.

**Proves:** regional management events observed in the Event History window (up to 90 days), with event source/name, time, resource references, and available principal/session context.

**Does not prove:** ownership, data-plane activity, or events older than the retention window. Missing events are a coverage gap, not proof that a change did not happen. The connector labels the 90-day limit and pagination caps.

## CloudWatch metrics

**API:** `cloudwatch:GetMetricData`, `cloudwatch:ListMetrics` (namespace `AWS/Lambda`).

**Proves:** invocation/error/duration datapoints exist for the selected period within the configured lookback (14 days by default).

**Does not prove:** who invoked the function or who owns it. Missing metrics can mean no traffic, a metric gap, or a permissions issue.

## Scalr resource usage, workspaces, runs, and state metadata

**API:** read-only Scalr API v3 (`/api/iacp/v3`). Resource usage is queried through `/reports/resource-usage` with the account-specific `filter[tf-resource-usage]` expression and included workspace/run/state/environment relationships.

**Proves:** a Terraform address and external resource identity are present in a Scalr workspace/state record; active versus historical status; workspace VCS repository/working directory; run actor and exact VCS revision when exposed by relationships; state version timestamps.

**Does not prove:** that the workspace is the sole owner, that a historical binding is current, or that an apply actor personally owns the resource. The filter value is not guessed; if it is missing or the API returns 401/403/429/schema changes, the source is marked as a gap.

**Retention caveat:** Scalr retains apply runs for three years, plan-only runs for 30 days, and the last 100 state files per workspace. Missing history is not proof of absence.

## Local Git

**Path:** `GIT_REPO_PATH`, default `demo-data/data-pipelines` for fixtures.

**Proves:** whether a commit SHA exists, commit metadata, paths, and small matching snippets in the selected repository/working directory.

**Does not prove:** that a file match is the deploying definition unless the exact commit/address is linked. The connector reports commit verification and file/history match limitations. It does not push or modify the repository.

## GitLab (optional)

**API:** GitLab REST project repository/commit/blob search with a project ID and read token.

**Proves:** project access, commit existence, and revision-scoped blob matches.

**Does not prove:** full history ownership; search may be unavailable or revision-scoped on the account tier. Local Git is the preferred history path.

## CloudWatch Omni (optional)

**Configuration:** `CLOUDWATCH_OMNI_URL` and `CLOUDWATCH_OMNI_SPACE`.

**Proves:** an optional reference/context link when a documented connector is configured.

**Does not prove:** ownership or complete operational state. The current release treats Omni as context only; it is never a required source.

## Local Terraform state backup (optional)

**Input:** a user-supplied `.tfstate` or state JSON file uploaded on the Investigate page.

**Proves:** a historical, point-in-time association between a Terraform address and a Lambda ARN/name in that snapshot, plus non-secret configuration such as runtime, handler, memory, timeout, and last-modified time.

**Does not prove:** current ownership, that the snapshot came from the expected workspace, or that the state was ever applied. The evidence carries `origin=user_supplied`. It can support a candidate lineage but cannot override exact live evidence, resolve insufficient access, or establish a current owner. Raw state, outputs, variables, environment values, sensitive attributes, and secrets are discarded before evidence/export/model use.

## MCP adapters (optional)

**Configuration:** `GROUNDTRUTH_MCP_SERVERS` plus `GROUNDTRUTH_MCP_ALLOWLIST`.

**Proves:** whatever an explicitly allowlisted read-only tool returns.

**Does not prove:** anything by default. MCP is disabled unless configured; unknown or write-capable tools are blocked, and tool output is untrusted. There is no shell/browser/file-write tool in the allowlist.

## Failure semantics

| Result | Meaning |
| --- | --- |
| `success` | Source read completed and returned usable data. |
| `partial` | Some data returned, but pagination, malformed records, or a sub-read failed. |
| `permission_denied` | Credentials exist but the source denied access. Not an empty result. |
| `not_configured` | Required endpoint/token/filter/path is missing. |
| `rate_limited` | The source throttled the read; retry instructions are shown. |
| `not_found` | The requested resource was not found in this source. |
| `failed` | Unexpected source failure; treated as a coverage gap. |

Required AWS/Scalr failures produce `INSUFFICIENT_ACCESS`; a failed optional source reduces coverage but does not fabricate an owner.
