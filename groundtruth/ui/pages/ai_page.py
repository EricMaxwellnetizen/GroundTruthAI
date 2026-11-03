from __future__ import annotations

import streamlit as st

from groundtruth.ui import components as ui
from groundtruth.ui import state


def render() -> None:
    result = state.current_result()
    if result is None:
        ui.header("AI explanation", "A grounded narrative — or a deterministic fallback.", "")
        ui.empty_state("No investigation loaded", "Run a fixture case to generate its explanation.")
        return
    ui.header(
        "AI explanation",
        "Muse Spark explains; the deterministic engine decides.",
        "The model receives only sanitized evidence collected by the connectors. It cannot change status, confidence, or ownership, and every factual claim must cite a known evidence ID.",
    )
    ui.fixture_banner(result.fixture, result.mode)
    explanation = result.ai_explanation
    if st.button("Regenerate explanation", type="primary", key="ai_regenerate"):
        with st.spinner("Building a grounded explanation..."):
            result.ai_explanation = state.ai_service().explain(result)
        st.session_state["result"] = result
        st.session_state["bundle"] = None
        explanation = result.ai_explanation
    if explanation is None:
        ui.empty_state("No explanation yet", "Generate one, or rerun the investigation to include it automatically.")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        label = "Muse Spark" if explanation.generated_by == "muse-spark" else "Deterministic fallback"
        foreground = "#155E56" if explanation.generated_by == "muse-spark" else "#9A5B13"
        background = "#E9F6F1" if explanation.generated_by == "muse-spark" else "#FCEFD8"
        st.markdown(ui.pill(label, foreground, background), unsafe_allow_html=True)
    with col2:
        st.metric("Model", explanation.model or "local template")
    with col3:
        st.metric("Tool calls", str(explanation.tool_calls_used))

    if explanation.generated_by == "deterministic_fallback":
        st.info(
            "Muse Spark was unavailable or returned an invalid response. This explanation was generated locally from the "
            "same evidence and does not change the deterministic result."
        )
    with st.container(border=True):
        st.markdown("**Summary**")
        st.write(explanation.summary)

    ui.section("Established facts", "Each statement is tied to at least one evidence record.")
    if explanation.established_facts:
        for fact in explanation.established_facts:
            with st.container(border=True):
                st.write(fact.statement)
                ui.evidence_chips(fact.evidence_ids, result=result)
                unknown = [item for item in fact.evidence_ids if result.evidence_by_id(item) is None]
                if unknown:
                    st.error(f"Citation validation failed for: {', '.join(unknown)}")
    else:
        st.caption("No established facts were returned.")

    if explanation.unresolved_questions:
        ui.section("Unresolved questions")
        for question in explanation.unresolved_questions:
            st.markdown(f"- {question}")

    if explanation.next_steps:
        ui.section("Suggested next steps", "Suggestions are operator actions, never automated changes.")
        for step in explanation.next_steps:
            with st.container(border=True):
                st.markdown(f"**{step.step}**")
                st.caption(step.reason)
                if step.evidence_ids:
                    ui.evidence_chips(step.evidence_ids, result=result)

    if explanation.warnings:
        ui.section("Warnings")
        for warning in explanation.warnings:
            st.warning(warning)

    st.caption(
        "The AI explanation is advisory. The deterministic status, confidence, and recommendation on the Lineage and "
        "Evidence report pages are authoritative."
    )
