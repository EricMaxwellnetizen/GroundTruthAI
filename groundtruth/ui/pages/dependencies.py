from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from groundtruth.ui import components as ui
from groundtruth.ui import state
from groundtruth.utils.urls import safe_url


def _activity(activity) -> None:
    if activity is None:
        ui.empty_state("No activity summary", "CloudWatch metrics were not available for this investigation.")
        return
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        ui.metric("Invocations", f"{activity.total_invocations:,.0f}", "Sum over the queried window")
    with col2:
        ui.metric("Errors", f"{activity.total_errors:,.0f}")
    with col3:
        ui.metric("Throttles", f"{activity.total_throttles:,.0f}")
    with col4:
        ui.metric("Datapoints", str(activity.invocation_datapoints))
    st.caption(
        f"Window {activity.window_start.isoformat(timespec='seconds')} to {activity.window_end.isoformat(timespec='seconds')} · "
        f"period {activity.period_seconds}s · last non-zero invocation {activity.latest_nonzero_invocations_at.isoformat(timespec='seconds') if activity.latest_nonzero_invocations_at else 'not observed'}"
    )
    if activity.no_datapoints:
        st.warning(
            "No CloudWatch datapoints were returned. This does not prove the function is unused — metrics may be unavailable, "
            "delayed, or the window may be outside retention."
        )
    if activity.limitations:
        for limitation in activity.limitations:
            st.caption(f"Limitation: {limitation}")


def render() -> None:
    result = state.current_result()
    if result is None:
        ui.header("Dependencies & activity", "Understand what the function touches.", "")
        ui.empty_state("No investigation loaded", "Run a fixture case to populate dependencies and activity.")
        return
    ui.header(
        "Dependencies & activity",
        "Configuration dependencies and observed activity.",
        "Dependency edges are inferred from Lambda configuration, execution-role metadata, or repository evidence. They are context, not proof of ownership.",
    )
    ui.fixture_banner(result.fixture, result.mode)
    dependencies = result.dependencies
    if dependencies:
        kinds = sorted({dependency.kind for dependency in dependencies})
        col1, col2 = st.columns([2, 2])
        with col1:
            selected_kinds = st.multiselect("Dependency kinds", kinds, default=kinds, key="dependency_kinds")
        with col2:
            st.caption(f"{len(dependencies)} dependency records in the investigation.")
        filtered = [dependency for dependency in dependencies if dependency.kind in selected_kinds]
        counts = (
            pd.DataFrame([{"Kind": dependency.kind, "Name": dependency.name} for dependency in filtered])
            .groupby("Kind")
            .size()
            .reset_index(name="Count")
        )
        if not counts.empty:
            figure = px.bar(
                counts,
                x="Kind",
                y="Count",
                color="Kind",
                color_discrete_sequence=["#0F766E", "#1D4ED8", "#7C3AED", "#0891B2", "#B54708"],
            )
            figure.update_layout(
                showlegend=False,
                height=260,
                margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Kind": dependency.kind,
                        "Name": dependency.name,
                        "Relationship": dependency.relationship,
                        "Direction": dependency.direction,
                        "Match": dependency.match_type.value,
                        "Evidence": dependency.evidence_id or "",
                        "ARN / ID": dependency.arn or dependency.identifier,
                    }
                    for dependency in filtered
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        with st.expander("Dependency evidence IDs", expanded=False):
            for dependency in filtered:
                st.markdown(f"- `{dependency.evidence_id or 'no evidence'}` — {dependency.kind}: {dependency.name}")
    else:
        ui.empty_state(
            "No dependencies recorded", "The connector did not return role, trigger, or repository dependency metadata."
        )

    ui.section("CloudWatch activity", "Metrics show activity, not who changed the resource.")
    _activity(result.activity)

    ui.section("CloudWatch Omni")
    omni = result.omni
    if omni is None or not omni.configured:
        st.caption("CloudWatch Omni is optional and not configured for this investigation.")
        if omni and omni.limitations:
            for limitation in omni.limitations:
                st.caption(f"Limitation: {limitation}")
    else:
        with st.container(border=True):
            st.markdown(f"**{ui.esc(omni.label, 160)}**")
            if omni.space:
                st.caption(f"Space: {omni.space}")
            url = safe_url(omni.url)
            if url:
                st.link_button("Open CloudWatch Omni", url)
            for limitation in omni.limitations:
                st.caption(f"Limitation: {limitation}")
        st.info("Omni is a contextual link only. It did not contribute ownership evidence.")
