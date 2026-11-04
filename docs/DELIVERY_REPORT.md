# Delivery report

**Release:** GroundTruth 1.0.0 - Meta Global AI Developer Hackathon MVP  
**Date:** 4 November 2026  
**Mode:** Fixture-first, read-only, local demo

## Status

The application is implemented end to end for the hackathon wedge: offline fixtures, deterministic lineage, ten-page Streamlit UI, bounded Muse Spark explanations with a guarded read-only tool loop, optional local Terraform state backup evidence, checksummed exports, SQLite history, read-only connectors, 127 tests, Docker, CI, and documentation.

Fixture mode is fully verified offline. Live reads were attempted only with read-only credentials. Their observed outcomes are recorded below without claiming unverified integrations.

## Live verification (observed)

Run on 4 November 2026 with the local `.env`. Secrets were never printed, logged, or included in this report.

| Source | Operation | Observed result | Classification |
| --- | --- | --- | --- |
| Meta Model API | Case A explanation, tool loop enabled | `generated_by=muse-spark`, `model=muse-spark-1.3`, 1 tool call, 10 grounded facts, `error=null`; deterministic status stayed `HISTORICAL_OWNER_FOUND` | **LIVE VERIFIED** |
| Scalr | `GET /api/iacp/v3/workspaces` with read-only token | `success`, 1 page, 0 workspace records | **LIVE READ VERIFIED** |
| Scalr | `/reports/resource-usage` and run/state join | `not_configured`: `SCALR_TF_RESOURCE_USAGE_FILTER` is unset; value is free-form and schema-specific | **BLOCKED-BY-HUMAN** |
| AWS | `sts:GetCallerIdentity` | HTTP 403 `InvalidClientTokenId`; connector reports `not_configured` and recommends `aws sso login` or a valid `AWS_PROFILE` | **BLOCKED-BY-HUMAN** |
| Git | Live Scalr run SHA join | No live Scalr resource-usage record and `GIT_REPO_PATH` is unset | **BLOCKED-BY-HUMAN** |
| GitLab | REST commit/blob reads | `GITLAB_PROJECT_ID` and `GITLAB_TOKEN` are unset | **NOT CONFIGURED** |
| MCP | Tool discovery/call | `GROUNDTRUTH_MCP_SERVERS` and allowlist are empty | **NOT CONFIGURED** |

Live Meta calls were outbound only to `https://api.meta.ai/v1`. AWS/Scalr operations were read-only; no Lambda invocation, apply, approval, state mutation, push, or deletion was attempted.

## Verified locally

| Check | Result |
| --- | --- |
| `python -m pytest -q` | 127 passed |
| `python -m ruff check .` | clean |
| `python -m ruff format --check .` | clean |
| `python -m compileall -q app.py groundtruth tests` | clean |
| `python -m pip_audit` | no known vulnerabilities |
| Export JSON Schema | all five fixture bundles validate against `fixtures/schemas/evidence_bundle.schema.json` |
| Fixture statuses | all five expected outcomes verified |
| Export integrity | checksum, schema, and redaction verified |
| AppTest pages | all 10 pages render empty and with a fixture result |
| Connector hardening | identity, CloudTrail, CloudWatch, Scalr failure modes/pagination, Git SHA/path safety, GitLab errors |
| Tool-loop guardrails | read tools only, call/turn/timeout budgets, repeated-call abort, MCP allowlist recheck, fallback |
| State-backup safety | raw/sensitive fields stripped, 8 MB cap, cannot override exact live evidence |
| Docker image | Rebuilt `groundtruth:1.0.0` on 4 November 2026; `/_stcore/health` returned `ok`; container ran as `groundtruth` (uid 10001) |
| Fresh virtual environment | Clean external venv installed from `requirements-dev.txt`; lint, format, compile, 127 tests, and audit all passed |
| CI parity | Local commands match `.github/workflows/ci.yml` (ruff check, ruff format --check, compileall, pytest, pip_audit) |

## Acceptance criteria

| Criterion | Status |
| --- | --- |
| App starts from documented fresh setup | Pass (fixture mode; fresh-venv install and Docker health verified 4 November 2026) |
| Fixture mode without credentials/network | Pass |
| Lambda investigation by ARN/name | Pass in fixture and implemented live path |
| Live AWS path or actionable blocker | **BLOCKED-BY-HUMAN**: STS `InvalidClientTokenId`; UI reports `not_configured` |
| Scalr resource-usage endpoint/schema, no guessed filter | Implemented with configurable filter and safe gap handling; **BLOCKED-BY-HUMAN** because the filter value is unset |
| Workspace/run lineage with exact VCS SHA | Fixture verified; live join blocked by missing filter/live run record |
| Git commit/file evidence with limitations | Fixture and local demo repository verified; live Scalr-SHA join blocked |
| CloudTrail labels 90-day management events | Connector and parsing verified by tests and fixture |
| CloudWatch invocations/errors/duration | Connector and parsing verified by tests and fixture |
| Deterministic status/confidence | Pass |
| AI explanation cannot change status | Pass via validation, bounded tool loop, and fallback; live Meta result observed unchanged |
| Multiple active owners hard stop | Pass |
| Permission gap is not empty result | Pass |
| Read-only, no mutation tools | Pass |
| JSON/Markdown export with checksums | Pass |
| Secret/account redaction | Pass |
| Documentation agrees with behavior | Pass; live, fixture, and blocked states are separated |
| CI, Docker, reproducible dependencies | Pass; CI workflow configured, local CI-parity commands, fresh-venv install, and Docker non-root health all verified |

## Demo cases

- `A_historical_owner` -> `HISTORICAL_OWNER_FOUND`, HIGH
- `B_multiple_active_owners` -> `MULTIPLE_ACTIVE_OWNERS`, HIGH
- `C_candidate_lineage` -> `CANDIDATE_LINEAGE`, LOW
- `D_insufficient_access` -> `INSUFFICIENT_ACCESS`, UNKNOWN
- `E_current_owner` -> `CURRENT_OWNER_FOUND`, HIGH

## Important limitations

1. AWS live verification is blocked by invalid/expired default credentials; refresh credentials or set a valid `AWS_PROFILE`/SSO session.
2. Scalr resource-usage verification is blocked by the unset, schema-specific `SCALR_TF_RESOURCE_USAGE_FILTER`; do not guess it.
3. The live Scalr-VCS-Git join cannot be exercised until a real resource-usage record and `GIT_REPO_PATH` are available.
4. GitLab and MCP remain unconfigured.
5. CloudTrail Event History is regional management events, at most 90 days, and not last-used tracking.
6. Scalr history is finite; missing history is not proof of absence.
7. GitLab search is revision-scoped; local Git is the reliable history path.
8. Fixture repositories and commits are synthetic.
9. Hosted deployment and authentication are out of scope.
10. Static type checking (mypy/pyright) is not part of the acceptance gate; runtime models are validated by Pydantic, and Ruff, compileall, tests, and audit gate the release. The build contract permitted this only if compatible with the existing repository.

## Key paths

- `app.py` / `groundtruth/app.py` - Streamlit entrypoint.
- `groundtruth/services/lineage_engine.py` - deterministic trust core.
- `groundtruth/services/state_backup.py` - in-memory Terraform state parsing and exact-conflict rules.
- `groundtruth/connectors/` - read-only source adapters.
- `groundtruth/ai/` - Muse Spark explanation, grounded fallback, bounded read-only tool loop.
- `groundtruth/mcp/` - default-deny MCP client and policy.
- `groundtruth/exports/` - checksummed JSON/Markdown.
- `fixtures/cases/` - five synthetic cases.
- `fixtures/schemas/evidence_bundle.schema.json` - published export schema.
- `policies/aws-read-only-policy.json` - least-privilege AWS sample.
- `tests/` - 127 tests.
- `docs/DEMO_SCRIPT.md` - three-minute demo.

## Startup and demo commands

```powershell
# Fixture demo (no credentials needed)
Copy-Item .env.example .env
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
# Open http://localhost:8501 and click "Run this case" on A - Historical owner found.

# Verification
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m compileall -q app.py groundtruth tests
python -m pip_audit

# Docker
docker build -t groundtruth:1.0.0 .
docker run --rm -p 8501:8501 groundtruth:1.0.0
```

Demo walkthrough: `docs/DEMO_SCRIPT.md` (three minutes, fixture mode; fall back to the
deterministic explanation if the live model is unavailable).

## Human-only actions still open

- Refresh AWS credentials/SSO profile and supply the Scalr filter if live resource-level verification is required.
- Configure GitLab/MCP only if those sources are part of the submission narrative.
- Record and upload the demo video; choose the hackathon track; submit the portal entry.
- Push the local commit if the submission requires a remote update.
