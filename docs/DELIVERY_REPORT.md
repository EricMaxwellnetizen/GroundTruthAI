# Delivery report

**Release:** GroundTruth 1.0.0 - Meta Global AI Developer Hackathon MVP  
**Date:** 2 November 2026  
**Mode:** Fixture-first, read-only, local demo

## Status

The application is implemented end to end for the hackathon wedge: offline fixtures, deterministic lineage, ten-page Streamlit UI, bounded AI explanation, checksummed exports, SQLite history, read-only connectors, tests, Docker, CI, and documentation.

Live AWS/Scalr/GitLab/Meta calls are implemented but were not exercised with real credentials in this environment. The UI reports that honestly.

## Verified locally

| Check | Result |
| --- | --- |
| `python -m pytest -q` | 48 passed |
| `python -m ruff check .` | clean |
| `python -m ruff format --check .` | clean |
| `python -m compileall -q app.py groundtruth tests` | clean |
| `python -m pip_audit` | no known vulnerabilities |
| Fresh Streamlit startup | healthy at `/_stcore/health` |
| Browser fixture flow | Case A completed and rendered |
| AppTest empty pages | all 10 pages render without exceptions |
| AppTest result pages | all 10 pages render with a fixture result |
| Fixture statuses | all five expected outcomes verified |
| Export integrity | checksum and redaction verified |
| JSON/Markdown downloads | generated and inspected in tests |
| Browser screenshots | Home, Investigate, Lineage, Report, Multiple owners |
| Docker image | `groundtruth:1.0.0` built successfully; container served health `ok` as non-root `uid=10001` |

## Acceptance criteria

| Criterion | Status |
| --- | --- |
| App starts from documented fresh setup | Pass (local `.venv`; Docker image built and health-checked) |
| Fixture mode without credentials/network | Pass |
| Lambda investigation by ARN/name | Pass in fixture and implemented live path |
| Live AWS path or actionable blocker | Implemented, not credential-verified; UI shows blocker status |
| Scalr resource-usage endpoint/schema, no guessed filter | Implemented with configurable filter and safe gap handling |
| Workspace/run lineage with exact VCS SHA | Implemented; fixture verified |
| Git commit/file evidence with limitations | Implemented; local Git verified via fixture |
| CloudTrail labels 90-day management events | Implemented; fixture verified |
| CloudWatch invocations/errors/duration | Implemented; fixture verified |
| Deterministic status/confidence | Pass |
| AI explanation cannot change status | Pass via validation and fallback |
| Multiple active owners hard stop | Pass |
| Permission gap is not empty result | Pass |
| Read-only, no mutation tools | Pass |
| JSON/Markdown export with checksums | Pass |
| Secret/account redaction | Pass |
| Documentation agrees with behavior | Pass; live limitations called out |
| CI, Docker, reproducible dependencies | Pass (CI configured; Docker build and non-root health check verified) |

## Demo cases

- `A_historical_owner` -> `HISTORICAL_OWNER_FOUND`, HIGH
- `B_multiple_active_owners` -> `MULTIPLE_ACTIVE_OWNERS`, HIGH
- `C_candidate_lineage` -> `CANDIDATE_LINEAGE`, LOW
- `D_insufficient_access` -> `INSUFFICIENT_ACCESS`, UNKNOWN
- `E_current_owner` -> `CURRENT_OWNER_FOUND`, HIGH

## Important limitations

1. No real AWS, Scalr, GitLab, or Meta credentials were available; live behavior requires a test-account verification pass.
2. The guarded multi-turn Meta tool-calling loop is not enabled. The client supports tool calling, but the internal read-only tool bridge remains future work.
3. Scalr `filter[tf-resource-usage]` is account/schema-specific and must be configured; it is never hardcoded.
4. CloudTrail Event History is regional management events, at most 90 days, and not last-used tracking.
5. Scalr history is finite; missing history is not proof of absence.
6. GitLab search is revision-scoped; local Git is the reliable history path.
7. Fixture repositories and commits are synthetic.
8. Hosted deployment and authentication are out of scope.

## Key paths

- `app.py` / `groundtruth/app.py` - Streamlit entrypoint.
- `groundtruth/services/lineage_engine.py` - deterministic trust core.
- `groundtruth/connectors/` - read-only source adapters.
- `groundtruth/ai/` - Muse Spark explanation and fallback.
- `groundtruth/exports/` - checksummed JSON/Markdown.
- `fixtures/cases/` - five synthetic cases.
- `policies/aws-read-only-policy.json` - least-privilege AWS sample.
- `tests/` - 48 tests.
- `docs/DEMO_SCRIPT.md` - three-minute demo.
