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
            "Source": "Fixture mode",
            "State": "Ready offline",
            "Detail": f"{len(state.orchestrator().list_fixture_cases())} synthetic cases",
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
            "Detail": "Human allowlist required",
        },
    ]


def render() -> None:
    settings = state.settings()
    cases = state.orchestrator().list_fixture_cases()
    ui.header(
        "Resource lineage, with receipts",
        "Find the owner before you touch the resource.",
        "GroundTruth correlates exact AWS identity, Scalr state ownership, Git history, CloudTrail and CloudWatch evidence. "
        "The deterministic engine owns the status; Muse Spark only explains the evidence it is given.",
    )
    ui.fixture_banner(settings.mode == "fixture", settings.mode)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        ui.metric("Fixture cases", str(len(cases)))
    with col2:
        ui.metric("Saved investigations", str(state.repository().count()))
    with col3:
        ui.metric("AI mode", "Muse Spark" if settings.ai_configured else "Fallback")
    with col4:
        ui.metric(
            "Live sources", str(sum([settings.scalr_configured, settings.git_configured, settings.gitlab_configured]))
        )

    left, right = st.columns([1.35, 1])
    with left:
        ui.section(
            "Start with a known-answer case", "The five demo cases exercise every terminal status and confidence path."
        )
        for index, case in enumerate(cases):
            with st.container(border=True):
                top_left, top_right = st.columns([3, 1])
                with top_left:
                    st.markdown(f"**{case['label']}**")
                    st.caption(safe_text(str(case.get("summary") or ""), 320))
                with top_right:
                    expected = case.get("expected_status") or ""
                    st.markdown(ui.status_pill(str(expected)), unsafe_allow_html=True)
                    st.caption(f"Expected {case.get('expected_confidence') or ''} confidence")
                st.button(
                    "Run this case",
                    key=f"home_case_{case['case_id']}",
                    on_click=_open_case,
                    args=(case["case_id"], case["label"]),
                    width="stretch",
                )
    with right:
        ui.section("Recent investigations", "Metadata only; tokens and raw state are never stored.")
        recent = state.repository().list(limit=6)
        if recent:
            frame = pd.DataFrame(
                [
                    {
                        "Resource": item.resource_name,
                        "Status": item.status,
                    }
                    for item in recent
                ]
            )
            st.dataframe(
                frame,
                hide_index=True,
                width="stretch",
                column_config={
                    "Resource": st.column_config.TextColumn(width="small"),
                    "Status": st.column_config.TextColumn(width="large"),
                },
            )
        else:
            ui.empty_state("No saved investigations yet", "Run a fixture case to establish the demo path.")
        st.markdown(
            '<div class="gt-card"><h4>Read-only by design</h4><p>No apply, import, delete, invoke, or infrastructure mutation '
            "is exposed. Missing evidence is reported as a coverage gap, not proof of absence.</p></div>",
            unsafe_allow_html=True,
        )

    ui.section("Connection readiness", "A source is never marked connected until its test actually succeeds.")
    st.dataframe(pd.DataFrame(_source_readiness(settings)), hide_index=True, width="stretch")

    ui.section("How the answer is produced")
    step1, step2, step3 = st.columns(3)
    with step1:
        st.markdown(
            '<div class="gt-card"><h4>1. Collect exact identity</h4><p>AWS Lambda ARN, account, region, tags, execution role, '
            "triggers and metric activity.</p></div>",
            unsafe_allow_html=True,
        )
    with step2:
        st.markdown(
            '<div class="gt-card"><h4>2. Correlate ownership</h4><p>Scalr resource usage, workspace, run, state version, exact VCS SHA, '
            "and Git file history are joined by exact identifiers.</p></div>",
            unsafe_allow_html=True,
        )
    with step3:
        st.markdown(
            '<div class="gt-card"><h4>3. Explain with limits</h4><p>The engine sets status and confidence. Muse Spark cites evidence '
            "IDs or the app falls back deterministically.</p></div>",
            unsafe_allow_html=True,
        )
