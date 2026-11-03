# Roadmap

The hackathon release deliberately ships the narrow, defensible lineage wedge. The broader platform is preserved here so future work does not compromise the trust model.

## Phase 1 - Delivered in this release

- Read-only AWS Lambda discovery and detail.
- Resource identity normalization and exact-identity guardrails.
- Scalr resource-usage search, workspace/run/state correlation, and VCS SHA join where available.
- Current versus historical ownership classification.
- Local Git repository, working-directory, commit, and file-history correlation.
- CloudTrail management-event evidence with 90-day regional limits.
- CloudWatch Lambda invocation/error/duration evidence.
- Lambda dependency context: execution role, event source mappings, aliases, tags, function URL/event-invoke metadata when permitted.
- Evidence graph, timeline, status, match types, confidence rationale, coverage gaps, recommendations, and JSON/Markdown exports with checksums.
- Meta Muse Spark explanation grounded by evidence IDs, with strict validation and deterministic fallback.
- Offline fixture mode with five known-answer cases.
- Optional MCP adapters with default-deny read-only policy.
- Ten-page Streamlit UI, SQLite metadata history, tests, Docker packaging, and CI.

## Phase 1 - Remaining / deliberately deferred

- **Guarded Meta tool-calling loop.** The current client supports Chat Completions tool calling, but a multi-turn internal read-only tool bridge is not enabled. Keep it bounded by explicit tool schemas, read-only classification, allowlists, and deterministic revalidation if added.
- **Live credential verification.** AWS, Scalr, GitLab, and Meta paths need validation in a real test account with read-only credentials. Do not claim those integrations work until their connection tests succeed.
- **Hosted deployment.** A public hosted instance is intentionally not part of this release. It requires authentication, secret management, network controls, and an approved evidence-retention policy.

## Phase 2 - Brownfield IaC adoption assurance

- Reconcile live cloud inventory, current/historical Terraform/OpenTofu state, and repository HCL declarations.
- Map resources into an existing repository/module structure rather than generating a standalone project.
- Prevent one live resource from being bound to multiple IaC addresses or claimed by multiple active workspaces without explicit resolution.
- Detect missing resources, duplicates, ambiguous ownership, drift, unsupported types, missing dependencies, and incomplete scan coverage.
- Generate import-ready HCL and configuration-driven import blocks for supported resources using pinned OpenTofu/Terraform versions and provider schemas.
- Run a plan in an isolated sandbox; parse machine-readable plan output; block unintended creates, updates, replacements, deletions, and safety-critical unknowns.
- Produce an evidence bundle containing mappings, code diff, plan, policy result, approval, and post-adoption verification.
- Keep apply/import/state mutation behind an explicit human-controlled operation. Never autonomously apply to production.

## Phase 3 - Repository and workspace governance

- Searchable registry of repositories, roots, working directories, backend/workspace mappings, provider/account/region scopes, and discovered resource identities.
- Detect resources declared in multiple repositories, multiple state addresses, multiple active workspaces, conflicting Terraform/OpenTofu roots, or ambiguous ownership.
- Repository-directory manager and recommended ownership registry; support a canonical inventory without assuming one physical repository.
- Enforce a configurable one-resource/one-state-address ownership invariant.
- Track whether a Scalr run came from VCS, CLI, API, UI, schedule, or another supported source using returned metadata only.
- Investigate resources that disappear from active state or can no longer be located in the expected repository.

## Phase 4 - Console change capture and continuous lineage

- Detect console/CLI/API infrastructure changes using CloudTrail and configured event sources.
- Correlate events to resource identity and suggest an IaC patch or drift explanation.
- Never imply CloudTrail provides full configuration or intent.
- Maintain recurring resource-to-state/repository ownership reconciliation.
- Flag newly unattributed resources and ownership conflicts for review.
- Do not ban console operations; turn them into traceable evidence where possible.

## Phase 5 - Operations, dependency intelligence, and cost

- Extend the graph to S3, IAM, Glue, EventBridge, Step Functions, and additional AWS services.
- Diagnose Lambda/Glue failures using approved CloudWatch logs/metrics/traces with citations.
- Investigate unused resources with actual usage, logs, tags, dependency graph, retention, and business-owner evidence.
- Send DNR/cleanup alerts; propose deletion only after human-approved review. For test environments, support configurable deletion scheduling with approvals and allow/deny lists.
- Identify dependency groups and blast radius before proposed cleanup; never delete a chain because one node appears idle.
- Cost optimization with measured data and reproducible benchmarks; never claim savings without evidence.
- Goal-oriented environment/region replication: discover, reconcile, map dependencies, generate IaC, sandbox-test, calculate differences, and prepare an approved plan. Do not autonomously apply production replicas.

## Separate strategic exploration - self-hosted distributed state manager

A self-hosted, distributed, customer-hardware-only state management platform with AI-operated hosting is a separate control-plane business. It is a research direction only and must not be recreated inside GroundTruth. A future customer-VPC GroundTruth agent may run close to the customer's state and repositories, but it should consume existing state backends rather than replace Scalr/Terraform Cloud.

## Non-goals for this wedge

- Autonomous remediation or production applies.
- A public unauthenticated evidence portal.
- Ownership claims from weak name/tag similarity.
- Treating a permission gap as proof that no owner exists.
- A general-purpose cloud asset inventory or CMDB.
