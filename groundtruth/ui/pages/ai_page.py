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
        foreground = "#067647" if explanation.generated_by == "muse-spark" else "#B54708"
        background = "#ECFDF3" if explanation.generated_by == "muse-spark" else "#FFFAEB"
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

    _copilot(result)
    _trust_panel(result)


def _copilot(result) -> None:
    from groundtruth.services.copilot import SUGGESTED_QUESTIONS, CopilotService

    ui.section(
        "Ask GroundTruth",
        "Grounded copilot over this investigation. Answers cite evidence IDs or fall back deterministically.",
    )
    settings = state.settings()
    provider = "Llama open weights" if settings.ai_provider == "llama_open_weights" else "Muse Spark"
    st.caption(
        f"Provider: {provider} ({settings.active_model})"
        if settings.ai_configured
        else "Deterministic copilot (configure a model in Settings for Muse Spark / Llama)."
    )
    cols = st.columns(len(SUGGESTED_QUESTIONS))
    picked = None
    for col, question in zip(cols, SUGGESTED_QUESTIONS):
        with col:
            if st.button(question, key=f"copilot_q_{question[:18]}", width="stretch"):
                picked = question
    typed = st.chat_input("Ask about owner, actors, safety, evidence…", key="copilot_input")
    question = typed or picked
    history = st.session_state.setdefault("copilot_history", [])
    if question:
        with st.spinner("Checking the evidence…"):
            answer = CopilotService(settings).ask(result, question)
        history.append((question, answer))
        st.session_state["copilot_history"] = history[-6:]
    for past_q, past_a in history:
        with st.chat_message("user"):
            st.write(past_q)
        with st.chat_message("assistant"):
            st.write(past_a.answer)
            st.caption(f"Source: {past_a.generated_by}" + (f" · {past_a.model}" if past_a.model else ""))
            ui.evidence_chips(past_a.evidence_ids, result=result)


def _trust_panel(result) -> None:
    ui.section(
        "Trust & evaluation",
        "Self-checks judges can reproduce. Deterministic verdicts are scored against every known-answer scenario.",
    )
    orchestrator = state.orchestrator()
    cases = orchestrator.list_fixture_cases()
    correct = 0
    for case in cases:
        try:
            outcome = orchestrator.run_fixture(case["case_id"])
        except Exception:
            continue
        if outcome.status.value == case.get("expected_status") and outcome.confidence.value == case.get(
            "expected_confidence"
        ):
            correct += 1
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Scenario accuracy", f"{correct}/{len(cases)}")
    with c2:
        known = set(result.evidence_ids)
        cited = [
            fid
            for fact in (result.ai_explanation.established_facts if result.ai_explanation else [])
            for fid in fact.evidence_ids
        ]
        valid = sum(1 for fid in cited if fid in known)
        st.metric("Citation validity", f"{valid}/{len(cited)}" if cited else "n/a")
    with c3:
        st.metric("Evidence records", str(len(result.evidence)))
    st.caption(
        "Guarantees: weak name matches never override exact identity; two active owners hard-block adoption; "
        "tag/commit text is treated as untrusted data, never as instructions; the model cannot change status, confidence, or ownership."
    )
