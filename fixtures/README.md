# Fixtures

Everything in this directory is synthetic. No production account IDs, ARNs, customer names, commits, or secrets are stored here.

## `cases/`

Five known-answer investigations consumed by fixture mode:

| Case | Expected status | Expected confidence |
| --- | --- | --- |
| `A_historical_owner` | `HISTORICAL_OWNER_FOUND` | `HIGH` |
| `B_multiple_active_owners` | `MULTIPLE_ACTIVE_OWNERS` | `HIGH` |
| `C_candidate_lineage` | `CANDIDATE_LINEAGE` | `LOW` |
| `D_insufficient_access` | `INSUFFICIENT_ACCESS` | `UNKNOWN` |
| `E_current_owner` | `CURRENT_OWNER_FOUND` | `HIGH` |

The loader replaces `$DEMO_HEAD_SHA`, `$DEMO_HISTORICAL_SHA`, and `$DEMO_REPO_PATH` from the generated demo repository manifest. See `groundtruth/connectors/fixture.py` and `groundtruth/demo_repo.py`.

## `schemas/`

`evidence_bundle.schema.json` is the published JSON Schema (Draft 2020-12) for exported evidence bundles. `tests/test_export_schema.py` validates every fixture export against it. The schema is shape-only; SHA-256 integrity and semantic redaction are verified separately by `EvidenceBundle.verify_checksum()` and the export tests.

## Demo repository

The demo Git repository is generated at `demo-data/data-pipelines` when fixture mode runs. It is intentionally ignored by Git and is not stored under `fixtures/repos/`; an empty `repos/` directory would only invite stale clones. Use `GIT_REPO_PATH` for a real local clone.
