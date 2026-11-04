# Three-minute demo script

Start locally:

```powershell
.venv\Scripts\Activate.ps1
streamlit run app.py
```

The sidebar must show **DEMO / FIXTURE DATA**. If live credentials are unavailable, keep fixture mode; never imply a live scan occurred.

## 0:00-0:20 - The problem

> A Lambda is live in production, but it is missing from the Terraform repository and Scalr workspace we expect. Before deleting or re-importing it, I need to know who managed it, which commit defined it, and where the evidence ends.

Show the Home page: "Find the owner before you touch the resource."

## 0:20-0:50 - Run a known-answer investigation

Click **Run this case** on **A - Historical owner found**.

Point out:
- the five fixture cases cover every terminal status,
- fixture mode is offline and clearly labeled,
- the task runs in the background with stage-by-stage progress,
- the result remains deterministic even when the AI is disabled.

## 0:50-1:35 - Follow the evidence chain

Open **Lineage overview**.

Show:
- `HISTORICAL_OWNER_FOUND` and `HIGH` confidence,
- "No active state binding was found, but 1 historical Scalr binding(s) match the exact ARN",
- resource identity and evidence count,
- the historical manager, Terraform address `module.orders.aws_lambda_function.transformer`,
- the exact VCS revision and working directory where available.

Then open **Evidence graph** and **Timeline** briefly:
- exact matches are visually distinct from inferred/candidate edges,
- timestamps and source labels are visible,
- gaps are labeled instead of hidden.

## 1:35-2:00 - Show uncertainty and the report

Open **Evidence report**.

Show:
- 12 evidence records and coverage gaps,
- redaction applied,
- SHA-256 checksum verified,
- JSON and Markdown downloads,
- the report contains evidence, limitations, and the advisory explanation only.

## 2:00-2:25 - Duplicate-owner hard stop

Return Home and run **B - Multiple active owners**.

Open **Lineage overview**. Show:
- `MULTIPLE_ACTIVE_OWNERS`,
- "2 active Scalr workspaces claim the same Lambda ARN",
- adoption is unsafe and blocked,
- the app does not silently choose a winner.

## 2:25-2:45 - Close

> GroundTruth does not guess who owns production infrastructure. It finds the evidence, or shows exactly where the evidence ends. Deterministic code owns the status; Muse Spark only explains it.

If asked about live data: the Meta explanation and Scalr `/workspaces` read were observed live on 4 November 2026; AWS resource-level reads are blocked by invalid credentials, and the Scalr resource-usage filter, GitLab, and MCP remain unconfigured. The demo therefore stays in fixture mode. The Settings page reports unconfigured or failed sources honestly and never marks them connected without a successful connection test.
