from __future__ import annotations

import pandas as pd
import streamlit as st

from groundtruth.ui import components as ui
from groundtruth.ui import state
from groundtruth.ui.tasks import start_fixture
from groundtruth.utils.redaction import safe_text


def _open_case(case_id: str, label: str) -> None:
    start_fixture(case_id, label)
    st.session_state["nav"] = "Investigate"


def _source_readiness(settings) -> list[dict[str, str]]:
    return [
        {
            "Source": "Simulated environment",
            "State": "Connected",
            "Detail": f"Northgate Production mirror · {len(state.orchestrator().list_fixture_cases())} scenarios",
        },
        {
            "Source": "AWS Lambda",
            "State": "Configured, not tested" if settings.aws_configured else "Not configured",
            "Detail": f"Region {settings.aws_region}",
        },
        {
            "Source": "Scalr",
            "State": "Configured, not tested" if settings.scalr_configured else "Needs URL, token, filter",
            "Detail": settings.scalr_base_url or "SCALR_BASE_URL is empty",
        },
        {
            "Source": "Local Git",
            "State": "Configured, not tested" if settings.git_configured else "Optional, not configured",
            "Detail": settings.git_repo_path or "Set GIT_REPO_PATH",
        },
        {
            "Source": "GitLab REST",
            "State": "Configured, not tested" if settings.gitlab_configured else "Optional, not configured",
            "Detail": settings.gitlab_base_url,
        },
        {
            "Source": "Meta Muse Spark",
            "State": "Configured, not tested" if settings.ai_configured else "Deterministic fallback",
            "Detail": settings.meta_model,
        },
        {
            "Source": "MCP adapters",
            "State": f"{len(settings.mcp_servers)} server(s), default deny"
            if settings.mcp_servers
            else "Optional, not configured",
            "Detail": "Explicit allowlist required",
        },
    ]


def _automation_panel(settings, cases) -> None:
    from pathlib import Path

    from groundtruth.services.actions import ActionExecutor
    from groundtruth.services.automation import AutomationPolicy, run_automation

    from groundtruth.services.risk import queue_from_cases

    ranked = queue_from_cases(cases)
    ui.section(
        "Risk command queue",
        "Every function ranked by deterministic risk (status, activity, coverage). Critical items first — this is your triage order for the day.",
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Function": item.function_name,
                    "Risk": item.score,
                    "Band": item.band,
                    "Outcome": ui.status_label(item.status),
                    "Next action": item.next_action,
                    "Why": " · ".join(item.factors[1:]) or item.factors[0],
                }
                for item in ranked
            ]
        ),
        hide_index=True,
        width="stretch",
        column_config={"Risk": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d")},
    )
    attention_count = sum(1 for item in ranked if item.status != "CURRENT_OWNER_FOUND")
    ui.section(
        "Needs attention",
        f"{attention_count} function(s) need an ownership decision. Automation prepares reattributions for historical owners; disputes and deletions always wait for a human.",
    )
    policy = AutomationPolicy(enabled=settings.automation_enabled)
    st.caption(
        f"Automation policy: {'enabled' if policy.enabled else 'disabled'} (Settings → Automation & freshness). Live mode is plan-only."
    )
    if st.button("Run automation sweep", key="home_automation_run"):
        orchestrator = state.orchestrator()
        with st.spinner("Investigating every function and applying the policy…"):
            results = []
            for case in cases:
                try:
                    results.append(orchestrator.run_fixture(case["case_id"]))
                except Exception:
                    continue
            executor = ActionExecutor(
                Path(settings.project_root) / ".groundtruth" / "action_audit.jsonl",
                allow_live=settings.allow_live_actions,
            )
            outcomes = run_automation(results, policy, executor)
        for outcome in outcomes:
            st.markdown(f"- **{outcome['function']}** — {outcome['outcome']}: {outcome['detail']}")


def render() -> None:
    settings = state.settings()
    cases = state.orchestrator().list_fixture_cases()
    from groundtruth.services.risk import queue_from_cases as _queue

    inventory_count = len(_queue(cases))
    ui.header(
        "Northgate Production · ap-south-1",
        "Operations overview",
        "Track Lambda ownership across AWS and Scalr, investigate resources whose manager is unclear, and resolve conflicts before any change is planned.",
    )
    ui.fixture_banner(settings.mode == "fixture", settings.mode)

    conflicts = sum(1 for c in cases if c.get("expected_status") == "MULTIPLE_ACTIVE_OWNERS")
    gaps = sum(1 for c in cases if c.get("expected_status") == "INSUFFICIENT_ACCESS")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        ui.metric("Functions tracked", str(inventory_count), "Distinct functions in the current environment")
    with col2:
        ui.metric(
            "Ownership conflicts",
            str(conflicts),
            "Require resolution before adoption" if conflicts else "No blocking conflicts",
        )
    with col3:
        ui.metric("Access gaps", str(gaps), "Sources that could not be checked")
    with col4:
        ui.metric("Saved investigations", str(state.repository().count()), "Metadata history on this machine")

    left, right = st.columns([1.45, 1])
    with left:
        ui.section(
            "Investigation scenarios",
            "Prebuilt investigations covering every ownership outcome. Open one to review the full evidence chain.",
        )
        for case in cases:
            with st.container(border=True):
                top_left, top_right = st.columns([3, 1])
                with top_left:
                    st.markdown(f"**{case['label']}**")
                    st.caption(safe_text(str(case.get("summary") or ""), 320))
                with top_right:
                    st.markdown(ui.status_pill(str(case.get("expected_status") or "")), unsafe_allow_html=True)
                    st.caption(f"{case.get('expected_confidence') or ''} confidence")
                st.button(
                    "Open investigation",
                    key=f"home_case_{case['case_id']}",
                    on_click=_open_case,
                    args=(case["case_id"], case["label"]),
                    width="stretch",
                )
    with right:
        ui.section("Recent investigations", "Stored locally. Tokens and raw state are never persisted.")
        recent = state.repository().list(limit=6)
        if recent:
            frame = pd.DataFrame(
                [
                    {
                        "Function": item.resource_name,
                        "Outcome": ui.status_label(item.status),
                    }
                    for item in recent
                ]
            )
            st.dataframe(frame, hide_index=True, width="stretch")
        else:
            ui.empty_state("No investigations yet", "Open a scenario to populate this history.")
        st.markdown(
            '<div class="gt-card"><h4>Investigations never mutate</h4><p>Reads are read-only. Changes happen only in the governed Action Center — planned, confirmed, audit-logged. '
            "A missing record is reported as a coverage gap — never as proof that no owner exists.</p></div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="gt-card" style="margin-top:0.7rem;"><h4>How ownership is decided</h4><p>Exact ARN and state-address joins outrank name similarity. '
            "Two active owners is a hard stop. The deterministic engine decides; Muse Spark only explains.</p></div>",
            unsafe_allow_html=True,
        )

    _automation_panel(settings, cases)

    ui.section(
        "Environment connections",
        "A source counts as connected only after its read test succeeds. Configured is not connected.",
    )
    st.dataframe(pd.DataFrame(_source_readiness(settings)), hide_index=True, width="stretch")
