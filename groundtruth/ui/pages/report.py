from __future__ import annotations

import streamlit as st

from groundtruth.exports import export_json, export_markdown
from groundtruth.ui import components as ui
from groundtruth.ui import state


def render() -> None:
    result = state.current_result()
    if result is None:
        ui.header("Evidence report", "A portable, checksummed evidence bundle.", "")
        ui.empty_state("No investigation loaded", "Run a fixture case to build its report.")
        return
    settings = state.settings()
    ui.header(
        "Evidence report",
        "Share the reasoning, not the secrets.",
        "Exports contain evidence, coverage, limitations, and the advisory explanation. Account IDs are redacted by default; tokens, state values, and environment variables are never included.",
    )
    ui.fixture_banner(result.fixture, result.mode)
    redact = st.toggle(
        "Redact AWS account IDs",
        value=settings.redact_account_ids,
        key="report_redact",
        help="Recommended. The default is controlled by GROUNDTRUTH_REDACT_ACCOUNT_IDS.",
    )
    json_text, json_bundle = export_json(result, redact=redact)
    markdown_text, _markdown_bundle = export_markdown(result, redact=redact)
    checksum = json_bundle.integrity.checksum if json_bundle.integrity else ""
    verified = json_bundle.verify_checksum()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Evidence records", str(len(result.evidence)))
    with col2:
        st.metric("Coverage gaps", str(len(result.coverage_gaps())))
    with col3:
        st.metric("Redaction", "Applied" if redact else "Off")
    with col4:
        st.metric("Checksum", "Verified" if verified else "Not verified")

    with st.container(border=True):
        st.markdown("**SHA-256 integrity checksum**")
        st.code(checksum, language=None)
        st.caption(
            "The checksum is computed over the bundle payload excluding the integrity block. Recompute it after any edit "
            "to confirm the export was not altered."
        )
        if not verified:
            st.error("The generated bundle failed its own checksum verification.")

    download1, download2 = st.columns(2)
    with download1:
        st.download_button(
            "Download JSON bundle",
            data=json_text,
            file_name=f"groundtruth_{result.investigation_id}.json",
            mime="application/json",
            width="stretch",
            type="primary",
        )
    with download2:
        st.download_button(
            "Download Markdown report",
            data=markdown_text,
            file_name=f"groundtruth_{result.investigation_id}.md",
            mime="text/markdown",
            width="stretch",
        )

    st.markdown("**Report contents**")
    st.dataframe(
        {
            "Included": [
                "Resource identity and tags",
                "Deterministic status, confidence, and rule",
                "Current and historical owners",
                "Repository lineage",
                "Actors, CloudTrail events, CloudWatch activity",
                "Dependencies and Omni link",
                "Evidence and coverage gaps",
                "Recommendation and unresolved questions",
                "Advisory AI explanation",
            ],
            "Redaction": ["Account IDs only" if redact else "None"] * 9,
        },
        hide_index=True,
        width="stretch",
    )

    with st.expander("Markdown preview", expanded=False):
        st.markdown(markdown_text)
    with st.expander("JSON preview (first 16,000 characters)", expanded=False):
        st.code(json_text[:16000], language="json")
        if len(json_text) > 16000:
            st.caption(f"Preview truncated. Full download is {len(json_text):,} characters.")
    st.caption(
        "Fixture reports are demonstration artifacts. They are explicitly labelled as synthetic in both formats."
    )
