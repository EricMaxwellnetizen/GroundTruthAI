# GroundTruth Build Notes

**Build date:** 4 November 2026
**Release:** Hackathon MVP 1.0
**Local toolchain:** `.venv` Python 3.12.13, Streamlit 1.66.1, boto3 1.43, Pydantic 2.14

## Reconnaissance

- The repository contained only three specification documents: `MASTER_BUILD_PROMPT.md`, `PRODUCT_MANUAL.md`, and `GroundTruth_Meta_Hackathon_Build_Pack.md`.
- No application, tests, dependency manifest, environment file, or Git repository existed.
- No AWS, Scalr, GitLab, or Meta credentials were present in the environment.
- Docker, Git, Node.js, uv, and Python 3.12 are available locally.

## Default stack selected

The repository had no useful application, so the preferred default stack from the build contract is used:

- Python 3.12, Streamlit, boto3, requests, Pydantic v2, NetworkX, Plotly, OpenAI SDK against the Meta Model API.
- Modular `groundtruth` service layer so the lineage engine is independent of Streamlit and AI.
- pytest and Ruff for QA.
- SQLite for investigation metadata only.

## Implementation plan

1. Configuration, structured logging, typed models, connector result contract.
2. Deterministic identity normalization and lineage engine.
3. Five labelled fixture cases (current owner, historical owner, duplicate active owners, candidate-only, insufficient access) with a real local Git demo repository.
4. Read-only live connectors: AWS Lambda, CloudTrail Event History, CloudWatch metrics, Scalr REST, local Git, GitLab REST, Omni link context.
5. Evidence graph, timeline, coverage, deterministic recommendations, JSON/Markdown exports with checksums.
6. Meta Muse Spark explanation with strict validation, deterministic fallback, a guarded bounded read-only tool loop, and default-deny MCP allow-list registry.
7. Streamlit UI with demo/live modes, background investigations, cancellation, all required screens, and permanent DEMO DATA labelling.
8. Tests, lint, format, compile, secret scan, dependency audit, clean-start verification.
9. Docker, CI, documentation, demo script, pitch, screenshots, and delivery report.

## Final delivery status

- All application layers are implemented: fixture/live orchestration, seven-status engine, guarded AI tool loop, state-backup evidence, exports, SQLite, MCP policy, and ten UI pages.
- Local verification: 127 tests pass; Ruff lint/format clean; compileall clean; `pip-audit` reports no known vulnerabilities; AppTest renders all ten pages; fresh Streamlit startup and browser fixture flow were previously verified.
- Docker packaging verified locally: `groundtruth:1.0.0` built successfully, served `/_stcore/health` with `ok`, and ran as non-root `uid=10001`.
- Screenshots are in `docs/images/` for Home, Investigate, Lineage, Report, and Multiple active owners.
- Live Meta Muse Spark explanation verified on 4 November 2026 (`muse-spark-1.3`, 1 tool call, status unchanged). Scalr `/workspaces` read succeeded with 0 records. AWS STS returned `InvalidClientTokenId`; the AWS resource path is blocked pending valid credentials. The Scalr resource-usage filter, GitLab, and MCP remain unconfigured.
- The Scalr filter remains a required human-supplied, schema-derived value. The demo intentionally uses fixture mode.

## Assumptions and boundaries

- Live connectors are implemented but cannot be verified against the user's private AWS/Scalr/GitLab/Meta accounts without credentials. Every unverified integration is labelled as such.
- `SCALR_TF_RESOURCE_USAGE_FILTER` is required by the Scalr endpoint. The current Scalr OpenAPI definition checked on 2 November 2026 declares it as a free-form string and does not publish an enum. GroundTruth therefore never guesses it; the connector returns an actionable configuration error until a human supplies the value.
- The demo Git repository is generated locally with deterministic commits, so the fixture chain Scalr run → VCS revision → Git commit is a real Git join even offline.
- Meta Model API details were verified against the current official cookbook: `base_url=https://api.meta.ai/v1`, model `muse-spark-1.3`, Chat Completions tool calling with `tool_choice` limited to `auto`.
- No destructive control exists in the MVP. Approval/apply/import/delete/invoke/state mutation paths are absent.
