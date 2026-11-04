# GroundTruth — Product Manual

**Tagline:** Find the owner before you touch the resource.  
**Product:** GroundTruth — AWS Resource Lineage Investigator  
**Release intent:** Meta Global AI Developer Hackathon MVP  
**Default mode:** Local-first and read-only

> This manual describes the product behavior the build agent is instructed to implement. Follow the actual repository README and in-app configuration labels if implementation details differ. A live integration is not considered connected until its connection test succeeds.

---

## 1. What is GroundTruth?

GroundTruth helps cloud engineers investigate an AWS resource that is still running but cannot be found in the Terraform repository or Scalr workspace they expected.

Instead of manually jumping between AWS, Scalr, GitLab, state files, CloudTrail and CloudWatch, GroundTruth brings the available evidence into one investigation:

- Does the Lambda function exist in AWS now?
- Is it represented in a current Scalr resource/state record?
- Was it present in an accessible historical state or resource-usage record?
- Which Terraform address and workspace were associated with it?
- Which Scalr run and VCS commit can be joined to that workspace?
- Which Git repository, working directory, file and commit are relevant?
- What CloudTrail management events are available, and which principal/session is recorded?
- What recent Lambda invocation metrics are visible in CloudWatch?
- Which dependencies—such as its execution role or event source mapping—are observable?
- What cannot be established because of missing permissions, incomplete history or ambiguous identifiers?

GroundTruth then creates a timeline, evidence graph and downloadable investigation report. Meta Muse Spark can explain the evidence in plain English, but deterministic matching logic makes the ownership classification.

### The central promise

**GroundTruth does not guess who owns production infrastructure. It finds the evidence—or shows exactly where the evidence ends.**

## 2. Who should use it?

GroundTruth is designed for:

- Platform and cloud engineers responsible for Terraform/OpenTofu and cloud resource governance.
- DevOps engineers investigating resources that have moved between repositories/workspaces.
- AWS data engineers inheriting Lambda, S3, Glue or event-driven workloads.
- Cloud consultants performing infrastructure handovers or brownfield IaC migrations.

It is especially useful when a production resource exists in AWS but its current management owner is unclear.

## 3. What the first version supports

### Core MVP

- AWS Lambda discovery in a selected account and region.
- Lambda identity/configuration and selected dependency metadata.
- Scalr resource-usage search, workspace and run correlation, subject to account permissions and the current API schema.
- Local Git repository history correlation and optional GitLab API access.
- CloudTrail management-event evidence in the selected region and available Event History window.
- CloudWatch Lambda activity metrics such as `Invocations` and `Errors`.
- Optional CloudWatch Omni link/context when an authorized Omni URL is configured.
- Deterministic lineage statuses, confidence rationale, evidence timeline, graph, coverage report and exports.
- Meta Muse Spark evidence explanation when configured.
- Fixture/demo mode without cloud credentials.

### Not performed by the MVP

GroundTruth does not delete AWS resources, invoke Lambda functions, update infrastructure, trigger Scalr runs, approve applies, change Terraform/OpenTofu state, commit/push Git changes, or automatically import resources. It does not guarantee a resource is unused, identify a human creator in every case, or provide universal AWS coverage.

The longer-term roadmap includes brownfield IaC adoption assurance, repository/workspace conflict detection, OpenTofu/Terraform import proposals, sandbox plan validation, broader AWS services, continuous lineage, Lambda/Glue troubleshooting and cost optimization. Those capabilities must be clearly marked as future unless they are visibly implemented in your installed version.

## 4. Understand the key terms

| Term | Meaning |
|---|---|
| **Resource ARN** | AWS's globally structured identifier for a resource, including service, region and account context. For Lambda, this is the primary identity used by GroundTruth. |
| **Terraform address** | The address of a resource in Terraform/OpenTofu configuration/state, such as `module.orders.aws_lambda_function.processor`. |
| **State** | Terraform/OpenTofu's record associating declared resource addresses with real infrastructure objects. |
| **Workspace** | A Scalr-managed Terraform/OpenTofu execution/state context. |
| **Run** | A Scalr plan/apply workflow execution. Its actor/source/revision fields are not automatically proof that a particular resource was created by the run. |
| **VCS revision** | The commit SHA associated with a Scalr run, where returned by Scalr. |
| **Current owner** | The active state/workspace with an exact resource identity match in the evidence checked. |
| **Historical manager** | A workspace/state record associated with the exact identity in available historical evidence. This does not prove why the resource left the state. |
| **CloudTrail principal** | The AWS identity recorded for a management API event. It may be a person, assumed role, CI service, or AWS service. |
| **Git author** | Commit metadata. It is not necessarily the person who triggered the deployment or owns the service. |
| **Candidate match** | A weak match based on name, tag, path or other similarity; it is not verified ownership. |
| **Coverage gap** | A source, region, time window, page or permission the investigation could not inspect. |

## 5. Install GroundTruth

### 5.1 Prerequisites

For local installation, use:

- Python 3.11 or newer.
- Git.
- AWS CLI v2 if you want live AWS data.
- Read-only AWS access to the selected sandbox account.
- A Scalr account and read-only API token for Scalr lineage.
- A local clone of the relevant Git repository, or a read-only GitLab token for API mode.
- Meta Model API key for Muse Spark explanations (optional; the app must work without it).

Docker is optional if the repository provides a Dockerfile.

### 5.2 Clone the repository

```bash
git clone <groundtruth-repository-url>
cd <repository-folder>
```

### 5.3 Create a virtual environment

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 5.4 Configure environment

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Edit `.env` locally. Never commit the file or share a screenshot showing its contents.

Example configuration (fill only values you actually have):

```dotenv
GROUNDTRUTH_MODE=fixture
GROUNDTRUTH_LOG_LEVEL=INFO

AWS_PROFILE=groundtruth-readonly
AWS_REGION=ap-south-1

SCALR_BASE_URL=https://<your-account>.scalr.io
SCALR_API_TOKEN=
SCALR_TF_RESOURCE_USAGE_FILTER=

GIT_REPO_PATH=./demo-data/your-repository
GITLAB_BASE_URL=https://gitlab.com
GITLAB_PROJECT_ID=
GITLAB_TOKEN=

MODEL_API_KEY=
META_API_BASE_URL=https://api.meta.ai/v1
META_MODEL=muse-spark-1.3
AI_ENABLED=false

CLOUDWATCH_OMNI_URL=
CLOUDWATCH_OMNI_SPACE=
```

The `SCALR_TF_RESOURCE_USAGE_FILTER` value must come from the current Scalr OpenAPI/MCP schema. Do not guess it. If it is not verified, leave Scalr unconfigured and use fixture mode until the administrator supplies the correct value.

### 5.5 Configure AWS credentials

Use AWS SSO/profile or a read-only role rather than pasting long-lived access keys into GroundTruth.

For example:

```bash
aws configure sso
aws sso login --profile groundtruth-readonly
aws sts get-caller-identity --profile groundtruth-readonly
aws lambda list-functions --region <your-region> --profile groundtruth-readonly
```

Set `AWS_PROFILE` and `AWS_REGION` in `.env`.

### 5.6 Configure Scalr and Git

Request a read-only Scalr token with access to the account/workspaces/resource-usage/runs relevant to your investigation. For Git, use a read-only local clone. A GitLab API token should be restricted to the relevant project and must not have repository write permissions for the MVP.

### 5.7 Start the application

Use the command documented in the repository. For the default Streamlit implementation:

```bash
streamlit run app.py
```

Open the local URL shown in the terminal (commonly `http://localhost:8501`).

### 5.8 Optional MCP connections

GroundTruth may support MCP servers as an optional way to expose approved read tools to its investigation agent. Its direct AWS SDK, Scalr REST and Git/GitLab connectors remain the core data path.

MCP does not mean giving an AI model unrestricted access to AWS or GitLab. GroundTruth should discover the server's current tools, default them to denied, and enable only explicitly approved read-only tools. The backend must re-check the allow-list before each call.

Potential supported servers include AWS MCP/Agent Toolkit capabilities, the official Scalr MCP server, and GitLab's MCP server. Availability depends on server, auth method, account policy, product version and permitted toolsets. Check current official docs before connecting.

Meta Model API function calling is not itself an MCP transport. GroundTruth bridges selected MCP tools into a controlled internal tool registry, then exposes only validated read-only wrapper functions to Muse Spark. If MCP is unavailable, the direct connectors still work.

References: https://awslabs.github.io/mcp/servers · https://docs.scalr.io/docs/mcp-server · https://docs.gitlab.com/user/model_context_protocol/mcp_server/ · https://dev.meta.ai/docs/cookbook/tool-function-calling

## 6. First use: run the demo investigation

1. Open GroundTruth.
2. Select **Try demo investigation** or choose a clearly labelled fixture case.
3. Select the historical-owner example.
4. Start the investigation.
5. Review the resource identity and management status.
6. Open the timeline to see the historical state/workspace, associated run, VCS revision and Git evidence.
7. Review CloudTrail management events and CloudWatch invocation metrics separately.
8. Open the evidence graph and inspect the provenance label on every edge.
9. Select **Explain with Muse Spark** if AI is configured. Verify that every factual statement cites an evidence ID.
10. Download the JSON and Markdown evidence reports.

Fixture data is synthetic. A visible demo label must stay on the screen and in the export.

## 7. Investigate a real AWS Lambda

1. Select **Connect my environment**.
2. Verify the AWS account and region are correct. Use a sandbox or an account you are authorized to inspect.
3. Enter or select the Lambda ARN. Prefer the full ARN over a bare name.
4. Optionally expand **Existing Terraform state backup** and upload a `.tfstate` or state JSON file. It is parsed in memory on this machine; raw state, outputs, variables, environment values, sensitive attributes, and secrets are discarded. The parsed summary is user-supplied historical evidence and cannot override exact live evidence.
5. Select the source checks: AWS metadata, CloudTrail, CloudWatch, Scalr, Git/local repo and optional AI.
6. Start the investigation.
7. Wait for each connector to report its own status. A permission failure is not the same as an empty result.
8. Review the final status, confidence rationale, current/historical associations and evidence gaps.
9. Do not interpret a no-match result as proof of manual creation or abandonment.

## 8. Read the investigation result

### 8.1 Status meanings

| Status | What it tells you | What to do |
|---|---|---|
| `CURRENT_OWNER_FOUND` | One exact current state/resource usage match is associated with an active workspace. | Inspect that workspace before making a change. Do not import into another workspace. |
| `HISTORICAL_OWNER_FOUND` | An exact identity appears in accessible historical state/resource usage but not in current records checked. | Inspect the last known state/run and determine how management changed. The status does not establish why the resource left state. |
| `MULTIPLE_ACTIVE_OWNERS` | More than one active state/workspace claims the same remote object. | Stop. Resolve the duplicate ownership before any adoption or cleanup. |
| `CANDIDATE_LINEAGE` | The system found a name/tag/path similarity but no unique exact identity link. | Treat as a lead for manual investigation, not verified ownership. |
| `UNATTRIBUTED_IN_CHECKED_SOURCES` | No exact match appeared in all sources that were successfully checked. | Check other regions, accounts, repos, roles, backups, trails, and history. This is not proof that the resource has no owner. |
| `INSUFFICIENT_ACCESS` | A required source could not be checked due to missing permissions/configuration. | Request the minimum required read permission and rerun. |
| `IDENTITY_AMBIGUOUS` | Multiple accounts/regions/IDs could fit the input. | Supply a full ARN or correct the account/region context. |

### 8.2 Confidence meanings

- **High:** exact resource identity plus direct state/workspace association.
- **Medium:** exact identity appears in a strong source, but the full workspace/run/repository chain is incomplete.
- **Low:** only candidate name/tag/path/description evidence exists.
- **Unknown:** insufficient usable evidence.

Confidence is assigned by deterministic rules, not by Muse Spark. GroundTruth should explain the reason for the label.

### 8.4 AI explanation boundaries

When `AI_ENABLED=true` and a key is configured, Muse Spark may explain the already-computed result. The explanation is advisory. It must cite evidence IDs that exist in the bundle and must not change the status, confidence, owners, coverage, or recommendation.

The optional tool loop is bounded: it exposes only read-only tools over the current investigation, enforces turn/call/timeout budgets, aborts repeated calls, validates tool arguments, and rechecks any MCP allowlist immediately before a call. If the model or a tool fails, GroundTruth falls back to a deterministic explanation and keeps the deterministic result.

### 8.3 Current owner vs historical manager vs creator

These are not interchangeable:

- A current state binding suggests which workspace currently tracks the resource.
- A historical state binding shows where the resource appeared in an available earlier state record.
- A Scalr run actor is the user/service identity recorded for that run.
- A Git author/committer is commit metadata.
- A CloudTrail principal is the AWS identity recorded for a management API call.

A CI assumed role may perform an operation on behalf of a pipeline. Do not interpret it as a named individual unless there is separate, authorized evidence linking it to a human.

## 9. Activity and “last used” interpretation

GroundTruth intentionally separates management history from execution activity.

### CloudTrail

CloudTrail Event History records management events (control-plane API activity) in a Region for the last 90 days. It can show events such as function creation/configuration changes and the principal/session recorded. It is not, by itself, a history of Lambda invocations.

### CloudWatch

Lambda emits metrics such as `Invocations` to CloudWatch. GroundTruth may calculate the most recent returned time bucket where `Invocations` had a non-zero `Sum`.

The UI should call this **latest non-zero invocation metric bucket**, not “last used.” It is an approximate metric observation. A missing datapoint could mean no data returned, a query range issue, metrics not available, permission problems or a genuinely quiet period. Read the query window and data coverage before drawing conclusions.

### CloudWatch Omni

If your organization uses CloudWatch Omni, GroundTruth can provide a configured link or attach a sanitized Omni investigation reference. Omni is an optional observability companion; it is not required for GroundTruth's core lineage result. Do not assume it is enabled in every account/Region.

## 10. Evidence graph and timeline

The graph shows relationships such as:

`AWS Lambda ARN → Scalr resource usage → state version/address → workspace → run → VCS commit → Git repository/file`

CloudTrail and CloudWatch evidence form parallel branches:

- Lambda identity → CloudTrail management event → AWS principal/session → timestamp.
- Lambda identity → CloudWatch metric datapoints → invocation activity summary.

Every relationship must be labelled as exact, direct, candidate or inferred. A dependency (for example, a Lambda execution role) is not proof of IaC ownership.

The timeline sorts source events by their event time. Query time should be displayed separately when helpful. If sources use different timezones, normalize internally to UTC and display a clear local time/UTC indicator.

## 11. Export an evidence report

The JSON bundle should include:

- investigation ID and export timestamp;
- resource identity and whether data is fixture/live;
- deterministic status and confidence rule;
- current and historical ownership associations;
- evidence records with source, timestamp, source record ID, match method and limitations;
- run/repository/commit references;
- CloudTrail events and actor fields;
- CloudWatch metric window and summary;
- dependencies and graph edges;
- connector coverage and errors;
- unresolved questions and deterministic next action;
- AI explanation, if enabled, with evidence IDs;
- bundle schema version and checksum.

The Markdown report should explain the same facts in an engineer-readable format. Neither export should contain secrets, raw state, Lambda environment values, private keys or unnecessary raw payloads.

## 12. Troubleshooting

### AWS credentials are missing or expired

Run `aws sts get-caller-identity --profile <profile>`. For AWS SSO, run `aws sso login --profile <profile>`. Reopen/restart the app if it caches credentials. Never paste secrets into the UI or source code.

### `AccessDenied` for Lambda

Ask your AWS administrator for the minimum Lambda list/get/tag/event-source read actions required by the implemented connector. Confirm you are in the correct account and region.

### CloudTrail returns no event

Check the selected region, exact function name/ARN, query lookback, and event source. Event History is limited to 90 days and management events. A missing event is not proof that no operation occurred. A trail or CloudTrail Lake may be needed for older/custom event coverage.

### CloudTrail throttling

LookupEvents is rate limited. Retry after the application's backoff delay. Do not repeatedly refresh or launch parallel investigations against the same account/region.

### CloudWatch has no invocation datapoints

Check `cloudwatch:GetMetricData`/`GetMetricStatistics` permission, selected region, function-name dimension, time range and metric period. Read the coverage message. No datapoint is not proof of inactivity.

### Scalr returns 401 or 403

Check the base URL, token validity, expiration and the minimum read permissions for resource usage/workspaces/runs/state metadata. Ask your administrator to enable the required read tools if using MCP.

### Scalr resource-usage query complains about `filter[tf-resource-usage]`

This is a required endpoint parameter. Obtain the permitted value from the current Scalr OpenAPI/MCP schema and configure it; do not guess.

### Scalr returns no matching record

Check whether the query uses the right external ID/address, the active/inactive filter, account, resource type and pagination. Scalr retention is finite. No result means no result in the records queried, not proof of no historical management.

### Git commit SHA is missing

The local clone may be shallow or may not have fetched the relevant branch. Run `git fetch --all --tags` where allowed, then verify `git cat-file -e <sha>^{commit}`. Confirm the workspace repository identifier and working directory.

### Git search finds no exact function name

Terraform may construct resource names dynamically using variables, locals, `for_each`, `count`, modules or remote modules. GroundTruth should label a missing string search as inconclusive.

### Muse Spark is unavailable

Confirm the `MODEL_API_KEY`, current model ID, API base URL and account access. Disable AI and continue. Deterministic lineage, report and export must still work.

### The graph does not render

Use the evidence table/timeline fallback. The graph is a visualization of the same evidence; it is not the source of truth.

### Fixture information appears in a live investigation

Stop and inspect the mode/configuration. All synthetic data must be labelled `DEMO DATA`; do not combine fixture and live evidence without an explicit label on every record.

## 13. Security and privacy

- Use a sandbox account where possible.
- Use read-only credentials.
- Do not provide AWS administrator access to GroundTruth.
- Never share `.env` or tokens.
- Do not upload full production state files to an LLM. GroundTruth parses uploaded state locally and sends only a minimized summary.
- Do not send Lambda environment variables or code package URLs to Muse Spark.
- Restrict repository access to the project required for investigation.
- Treat AWS tags, resource descriptions and code comments as untrusted input.
- Review exports before attaching them to tickets or sharing them.
- Revoke tokens you no longer need.

## 14. Product limitations and roadmap

The first release focuses on AWS Lambda lineage. It is not a universal cloud inventory or complete IaC governance platform.

Planned roadmap areas include:

1. Broader AWS services: S3, IAM, Glue, EventBridge, Step Functions and associated dependencies.
2. Three-way resource/state/repository reconciliation and duplicate ownership prevention.
3. Repository-aware OpenTofu/Terraform import proposals.
4. Isolated plan execution and deterministic safety gating for adoption.
5. Post-adoption verification and evidence bundles.
6. Continuous lineage scans and alerts for newly unattributed resources.
7. Console/API change capture and suggested IaC patches.
8. Lambda/Glue failure diagnosis using logs/metrics/traces.
9. Evidence-backed cleanup recommendations and approved test-environment cleanup schedules.
10. Cost optimization, Glue script efficiency recommendations and resource simplification.
11. Goal-oriented environment/region replication with sandbox comparison and approval.
12. Self-hosted deployment and additional integrations.

These are future capabilities until implemented and tested in the version you are using.

## 15. Support information to collect

When reporting a problem, provide:

- GroundTruth version/commit.
- Python version and operating system.
- Fixture/live mode.
- Connector status (do not include tokens).
- Investigation ID.
- Sanitized error message and timestamp.
- Selected AWS region and resource type.
- Steps that reproduce the issue.

Do not attach raw state, credentials, secrets, private CloudTrail payloads, or confidential source code.

---

## Technical references

- Meta Model API: https://dev.meta.ai/docs/overview
- Scalr resource usage API: https://docs.scalr.io/reference/list_terraform_resource_instances_usage
- Scalr workspaces API: https://docs.scalr.io/reference/get_workspaces
- Scalr runs API: https://docs.scalr.io/reference/get_runs
- Scalr MCP server: https://docs.scalr.io/docs/mcp-server
- Scalr FAQ/retention: https://docs.scalr.io/docs/faq
- AWS Lambda GetFunction: https://docs.aws.amazon.com/lambda/latest/api/API_GetFunction.html
- AWS CloudTrail Event History: https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events.html
- AWS CloudTrail LookupEvents: https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_LookupEvents.html
- AWS Lambda CloudTrail logging: https://docs.aws.amazon.com/lambda/latest/dg/logging-using-cloudtrail.html
- AWS Lambda CloudWatch metrics: https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics.html
- AWS CloudWatch Omni: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch-omni.html
- GitLab Commits API: https://docs.gitlab.com/api/commits/
- GitLab Search API: https://docs.gitlab.com/api/search/
