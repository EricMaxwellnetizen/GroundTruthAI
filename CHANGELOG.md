# Changelog

## 1.0.0 - 2026-11-02

Hackathon MVP release.

### Added

- Read-only AWS Lambda, IAM role, CloudTrail, and CloudWatch connectors.
- Scalr resource-usage/workspace/run/state correlation with configurable filter and safe JSON:API parsing.
- Local Git and optional GitLab lineage with exact commit verification and bounded file/history matching.
- Optional CloudWatch Omni context.
- Deterministic lineage engine with seven terminal statuses, match hierarchy, confidence rules, evidence graph, timeline, dependencies, coverage gaps, and recommendations.
- Meta Muse Spark explanation with strict validation, evidence citations, and deterministic fallback.
- Offline fixture mode with five synthetic known-answer cases and a generated demo Git repository.
- Ten-page Streamlit UI with demo/live badges, background task progress, result history, and connection tests.
- Checksummed JSON and Markdown evidence exports with account-ID redaction.
- SQLite investigation metadata storage.
- Read-only MCP adapter with default-deny allowlist.
- AWS read-only IAM policy, `.env.example`, Dockerfile, CI workflow, and documentation.
- 48 automated tests including Streamlit AppTest page coverage.

### Verified

- `pytest`: 48 passed.
- `ruff check .`: clean.
- `ruff format --check .`: clean.
- `python -m compileall`: clean.
- `pip-audit`: no known vulnerabilities.
- Fresh Streamlit startup and fixture investigation flow exercised through AppTest and a headless browser.
- Docker image built; container rendered the health endpoint (`ok`) and ran as non-root `uid=10001`.
- JSON/Markdown export integrity checks.
- All five fixture statuses and confidence outcomes.

### Known limitations

- Live AWS, Scalr, GitLab, and Meta API calls were not exercised against real credentials in this build environment.
- The guarded multi-turn Meta tool-calling loop is not enabled.
- GitLab search is revision-scoped; local Git is the reliable history path.
- CloudTrail Event History is limited to regional management events and 90 days.
- Hosted deployment is intentionally out of scope.
- Fixture data and demo commits are synthetic.
