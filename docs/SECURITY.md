# Security and privacy

GroundTruth is designed as a read-only investigation aid. It is not a deployment, remediation, or approval tool.

## No-write posture

The application exposes no AWS write actions, Lambda invocations, Terraform apply/import commands, Scalr run approvals, repository pushes, or deletion controls. The MCP bridge is default-deny and filters tools by read-only classification and an explicit allowlist.

The UI does not offer controls that pretend to change infrastructure. Recommendations are advisory text; they are not executable actions.

## Credentials

- Prefer IAM Identity Center/SSO or an assumed role for AWS.
- Use a read-only Scalr token and a read-only GitLab token with the minimum project scope.
- Configure secrets through environment variables or a secret store, never in source files or SQLite.
- GroundTruth never echoes tokens back to the UI. The settings page shows only configured/not-configured state.
- Rotate or revoke any token that was exposed in a terminal, browser session, or log.
- `.env`, `.streamlit/secrets.toml`, local databases, and logs are ignored by Git and Docker build context.

## AWS permissions

The reference policy is [`policies/aws-read-only-policy.json`](../policies/aws-read-only-policy.json). It grants only:

- `sts:GetCallerIdentity`
- Lambda configuration/read APIs
- `iam:GetRole`
- `cloudtrail:LookupEvents`
- `cloudwatch:GetMetricData` and `cloudwatch:ListMetrics`

It does not grant `lambda:InvokeFunction`, `lambda:Update*`, `lambda:Delete*`, `iam:PassRole`, `cloudtrail:Put*`, or any write action. Scope resources down further where your environment permits. CloudTrail Event History and CloudWatch reads can return cross-resource metadata; use account/region boundaries and least privilege.

## Data handling

| Data | Handling |
| --- | --- |
| Lambda secrets/environment variables | Environment values are not collected or exported. Metadata is redacted. |
| Code package download URLs | Not retained in evidence or exports. |
| Terraform state/plans | Uploaded state is parsed in memory only; raw state, outputs, variables, environment values, sensitive attributes, and secrets are discarded. Only non-secret Lambda identity/configuration and matched addresses may enter evidence or the model bundle. |
| State upload lifetime | The parsed summary lives in the Streamlit session and the result bundle; the raw file is never written to disk or SQLite. |
| CloudTrail events | Reduced to timestamp, event name, resource, principal/session context, and source metadata; not stored indefinitely. |
| Git content | Paths, commit metadata, and small matched snippets only. Entire repositories are not uploaded to the model. |
| Account IDs | Redacted by default (`********9012`) in exports and many UI views. |
| Tokens | Never stored in SQLite, exports, or debug traces. |
| Investigation metadata | SQLite stores the redacted evidence bundle and summary metadata for local history. |

Tags, descriptions, code comments, commit messages, and resource metadata are treated as untrusted input. They are not interpreted as instructions by the deterministic engine.

## AI boundaries

- AI is disabled by default.
- The prompt contains normalized evidence and explicit limitations, not raw state, plans, secrets, or full repositories.
- The model must return strict JSON with allowed fields and known evidence IDs.
- The optional tool loop exposes only read-only tools over the already-computed investigation result. It enforces call/turn/timeout budgets, aborts repeated calls, validates arguments against a fail-closed schema, and rechecks the MCP allowlist immediately before every MCP call.
- Tools cannot issue new cloud calls or widen the resource scope beyond the current investigation.
- Validation rejects unknown evidence, extra fields, a different status, unsafe next steps, and uncited claims.
- Any missing key, network failure, malformed response, tool-loop failure, or validation error uses a deterministic fallback.
- The model cannot mutate the result, status, confidence, recommendation, or any connector.
- Model API calls are outbound only to the configured `META_API_BASE_URL`; the default is `https://api.meta.ai/v1`.

## MCP

MCP is optional and disabled unless `GROUNDTRUTH_MCP_SERVERS` is configured. The registry:

- rejects non-HTTP(S) or invalid server URLs,
- requires streamable HTTP transport,
- denies tools that are not explicitly allowlisted,
- classifies unknown or write-capable tools as blocked,
- treats tool output as untrusted evidence text.

Do not attach MCP servers that can mutate infrastructure. The guarded multi-turn tool loop is bounded, read-only, and default-deny; a tool that is not allowlisted is refused even if the model requests it.

## Threat model

| Threat | Mitigation |
| --- | --- |
| Accidental mutation | No write APIs or write controls; read-only policy; default-deny MCP. |
| Token leakage | Runtime environment only; redaction; no token persistence or echo. |
| Prompt injection in tags/commits | Deterministic matching owns status; AI validation and fallback; untrusted content bounded/redacted. |
| Hallucinated owner | Evidence-ID citations, status consistency checks, deterministic fallback, exact-match guardrails. |
| Empty result mistaken for no owner | Permission/config/pagination failures are explicit coverage gaps; required failures produce `INSUFFICIENT_ACCESS`. |
| Tampered export | SHA-256 checksum over the bundle payload; verification helper and UI checksum display. |
| Over-broad account data | Account/region guardrails, account ID redaction, local-only SQLite history. |

## Logging

Structured logs include investigation ID, connector, duration, page count, status, and error class. Secrets and full API responses are not logged by default. Debug mode is opt-in and still subject to redaction.

## Deployment

The primary target is a trusted local demo. Do not expose a public Streamlit instance containing real infrastructure evidence without authentication, network controls, secret management, and an explicit security review. A hosted deployment is outside this release. Docker runs as a non-root user and stores the SQLite database in `/app/data`.

## Reporting a problem

For a hackathon/demo build, document the issue in the repository issue tracker. For a production adaptation, treat token exposure, unexpected write capability, or real-evidence leakage as a security incident and revoke credentials immediately.
