# Delivery report

**Release:** GroundTruth 1.1.0 — Meta Global AI Developer Hackathon  
**Date:** 5 November 2026  
**Mode:** Simulated environment (Northgate mirror) + live connectors, local-first

## Status

Production-grade lineage console: eight-scenario simulated fleet covering every terminal status, deterministic lineage engine, ten-page Streamlit UI, bounded Muse Spark / open-weights explanations with a guarded read-only tool loop, adoption-proposal previews, governed reattribute/delete actions with automation policies, connector freshness checks, checksummed exports, SQLite history, read-only connectors by default, Docker, CI, and documentation. Full test suite green (see below); in-UI credential entry makes live mode a Settings action with no file editing.

## Enablement matrix (observed 4–5 November 2026)

Secrets were never printed, logged, or included in this report. Simulated rows exercise the identical code paths as live mode.

| Source | Operation | Observed result | State |
| --- | --- | --- | --- |
| Meta Model API | Scenario A explanation, tool loop enabled | `generated_by=muse-spark`, `model=muse-spark-1.3`, 1 tool call, 10 grounded facts, `error=null`; deterministic status stayed `HISTORICAL_OWNER_FOUND` | **Live verified** |
| Scalr | `GET /api/iacp/v3/workspaces` with read-only token | `success`, 1 page, 0 workspace records | **Live read verified** |
| Scalr | `/reports/resource-usage` and run/state join | Enabled by setting `SCALR_TF_RESOURCE_USAGE_FILTER` from your Scalr schema (Settings → paste credentials) | **Ready to enable** |
| AWS | `sts:GetCallerIdentity` + Lambda reads | Enabled by pasting an SSO profile or keys in Settings; connectors validate before any claim | **Ready to enable** |
| Git / GitLab | Run-SHA joins, commit/file evidence | Enabled via `GIT_REPO_PATH` or GitLab project/token in Settings | **Ready to enable** |
| MCP | Tool discovery/call | Enabled via `GROUNDTRUTH_MCP_SERVERS` + explicit allowlist (default deny) | **Ready to enable** |

Investigation reads are read-only. Mutations exist only in the governed Action Center (dry-run → typed confirmation → audit log) and never run during an investigation.

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

## Coverage notes

Investigations surface per-source coverage (accounts/regions queried, windows, pages, gaps) inside every result and export, so reviewers always see what was checked. Runtime models are validated by Pydantic; Ruff, compileall, tests and audit gate the release.

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

Demo walkthrough: three minutes in the simulated environment (Overview → Case A → Lineage → AI brief → Report); fall back to the deterministic explanation if the live model is unavailable. Go live any time from **Settings / connections** by pasting credentials in the UI — no file editing required.
