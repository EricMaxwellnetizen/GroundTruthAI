# Changelog

## 1.1.0 - 2026-11-05

Professional console release. Simulated data now mirrors production payload formats end to end; the heavy build-out (fleet breadth + adoption preview) ships on top of the 1.0.0 trust core without changing its rules.

### Changed

- Full UI redesign: enterprise console theme (slate/navy + teal), sans-serif type, stat tiles, status labels with plain-English names, navy sidebar with environment context. Streamlit theme updated to match.
- Simulated tenant is now **Northgate Production (mirror)**: account `739201845610`, Scalr host `northgate.scalr.io`, repositories `gitlab.com/northgate/*`, production-format workspace/run/state IDs, UUID CloudTrail event IDs, realistic principal ARNs/IDs and user agents. Internal `fixture` flags and export labelling are unchanged — simulated records are still identified as simulated in bundles and reports.
- Removed the "works offline / verified demo path" framing from the Investigate page; scenario and live flows now share one professional investigation surface.
- Demo Git repository content rewritten as production Terraform (no demo banners in file contents); author/remote now use the Northgate tenant.

### Added

- Three new scenarios, taking the pack to eight and covering every terminal status: `F_unattributed` (`UNATTRIBUTED_IN_CHECKED_SOURCES`), `G_identity_ambiguous` (`IDENTITY_AMBIGUOUS`, cross-account guardrail), `H_current_owner_fraud` (`eu-west-1` risk platform, `CURRENT_OWNER_FOUND`).
- Deterministic **adoption proposal preview** (`groundtruth/services/adoption.py`): generates a reviewable `aws_lambda_function` block + configuration-driven `import` block + pre-apply checklist from the verified identity. Hard-blocked for duplicate owners, ambiguous identity and insufficient access; warns when an owner already exists. Preview/download only — no apply path exists.
- Fleet risk summary on the Inventory page (conflicts, ambiguity, access gaps and unattributed functions with next actions).
- Execution-role dependency now surfaced for simulated functions (role ARN carried in safe attributes).

### Verified

- `pytest`: full suite green including 8-scenario determinism, adoption gating and AppTest coverage of all ten pages.
- `ruff check .`, `ruff format --check .`, `compileall`: clean.

## 1.0.0 - 2026-11-04

Hackathon MVP release.

### Added

- Read-only AWS Lambda, IAM role, CloudTrail, and CloudWatch connectors.
- Scalr resource-usage/workspace/run/state correlation with configurable filter and safe JSON:API parsing.
- Local Git and optional GitLab lineage with exact commit verification and bounded file/history matching.
- Optional CloudWatch Omni context.
- Deterministic lineage engine with seven terminal statuses, match hierarchy, confidence rules, evidence graph, timeline, dependencies, coverage gaps, and recommendations.
- Meta Muse Spark explanation with strict validation, evidence citations, and deterministic fallback.
- Guarded, bounded multi-turn tool loop exposing only read-only tools over the already-computed investigation result, with turn/call/timeout budgets, repeated-call abort, fail-closed argument schemas, and an MCP allowlist recheck before every call.
- Optional local Terraform state backup evidence, parsed in memory with sensitive fields stripped and exact-conflict rules; it cannot override live evidence.
- Published JSON Schema for evidence bundles.
- Offline fixture mode with five synthetic known-answer cases and a generated demo Git repository.
- Ten-page Streamlit UI with demo/live badges, background task progress, result history, and connection tests.
- Checksummed JSON and Markdown evidence exports with account-ID redaction.
- SQLite investigation metadata storage.
- Read-only MCP adapter with default-deny allowlist.
- AWS read-only IAM policy, `.env.example`, Dockerfile, CI workflow, and documentation.
- 127 automated tests including Streamlit AppTest page coverage, connector hardening, MCP transport, state-backup safety, tool-loop guardrails, and export schema validation.

### Verified

- `pytest`: 127 passed.
- `ruff check .`: clean.
- `ruff format --check .`: clean.
- `python -m compileall`: clean.
- `pip-audit`: no known vulnerabilities.
- Fresh external virtual environment: install from `requirements-dev.txt`, then lint, format, compile, test, and audit all pass.
- Fresh Streamlit startup and fixture investigation flow exercised through AppTest and a headless browser.
- Docker image built; container rendered the health endpoint (`ok`) and ran as non-root `uid=10001`.
- JSON/Markdown export integrity checks and JSON Schema validation for all five fixture bundles.
- All five fixture statuses and confidence outcomes.
- Live Meta explanation observed (`muse-spark-1.3`, one tool call, deterministic status unchanged).
- Live Scalr `/workspaces` read observed (`success`, 0 records).

### Known limitations

- Live AWS resource-level reads are blocked by invalid default credentials (`InvalidClientTokenId`). The connector reports `not_configured` rather than an empty result.
- Scalr resource-usage history is blocked because the schema-specific `SCALR_TF_RESOURCE_USAGE_FILTER` value is unset; it was not guessed.
- Live Scalr-to-Git joins, GitLab, and MCP remain unconfigured.
- GitLab search is revision-scoped; local Git is the reliable history path.
- CloudTrail Event History is limited to regional management events and 90 days.
- Hosted deployment is intentionally out of scope.
- Fixture data and demo commits are synthetic.
