from __future__ import annotations

import pandas as pd
import streamlit as st

from groundtruth.ui import components as ui
from groundtruth.ui import state
from groundtruth.utils.urls import safe_url


def render() -> None:
    result = state.current_result()
    if result is None:
        ui.header("Timeline", "Order the evidence by observation time.", "")
        ui.empty_state("No investigation loaded", "Run a fixture case to populate the timeline.")
        return
    ui.header(
        "Timeline",
        "When each piece of evidence was observed.",
        "Observed time is distinct from query time. CloudTrail, CloudWatch, Scalr and Git clocks are not synchronized; the order is evidentiary, not causal.",
    )
    ui.fixture_banner(result.fixture, result.mode)
    entries = result.timeline
    sources = sorted({entry.source.value for entry in entries})
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        selected_sources = st.multiselect("Sources", sources, default=sources, key="timeline_sources")
    with col2:
        matches = sorted({entry.match_type.value for entry in entries})
        selected_matches = st.multiselect("Match types", matches, default=matches, key="timeline_matches")
    with col3:
        ascending = st.toggle("Oldest first", value=True, key="timeline_order")
    filtered = [
        entry
        for entry in entries
        if entry.source.value in selected_sources and entry.match_type.value in selected_matches
    ]
    filtered.sort(key=lambda entry: (entry.observed_at, entry.evidence_id), reverse=not ascending)
    if not filtered:
        ui.empty_state("No events match", "Loosen the timeline filters.")
        return
    st.caption(f"{len(filtered)} of {len(entries)} evidence records shown.")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Observed (UTC)": entry.observed_at,
                    "Source": entry.source_label,
                    "Event": entry.title,
                    "Match": entry.match_type.value,
                    "Confidence": entry.match_confidence.value,
                    "Record": entry.source_record_id or "",
                    "Evidence": entry.evidence_id,
                }
                for entry in filtered
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    options = {f"{entry.evidence_id} · {entry.title}": entry for entry in filtered}
    selected = st.selectbox("Inspect evidence", list(options), key="timeline_selected")
    entry = options[selected]
    with st.container(border=True):
        st.markdown(f"**{ui.esc(entry.title, 220)}**")
        st.write(entry.detail or "No detail recorded.")
        st.caption(
            f"Observed {entry.observed_at.isoformat(timespec='seconds')} · queried {entry.queried_at.isoformat(timespec='seconds')} · "
            f"{entry.source_label} · {entry.match_type.value}"
        )
        url = safe_url(entry.source_url)
        if url:
            st.link_button("Open source record", url)

    cloudtrail_gap = next(
        (record for record in result.coverage if record.source == "cloudtrail" and record.is_gap),
        None,
    )
    if cloudtrail_gap:
        st.warning(
            "CloudTrail coverage is incomplete for this investigation. "
            f"Status: {cloudtrail_gap.status.value}. {cloudtrail_gap.error or 'No event history was available.'}"
        )
    st.caption(
        "CloudTrail Event History covers at most 90 days per region and does not include data events by default."
    )
