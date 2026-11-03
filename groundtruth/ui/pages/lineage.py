from __future__ import annotations

import pandas as pd
import streamlit as st

from groundtruth.models.lineage import OwnershipEvidence
from groundtruth.ui import components as ui
from groundtruth.ui import state
from groundtruth.utils.urls import safe_url


def _owner_card(owner: OwnershipEvidence, kind: str) -> None:
    workspace = owner.workspace
    with st.container(border=True):
        top_left, top_right = st.columns([3, 1])
        with top_left:
            st.markdown(f"**{ui.esc(workspace.name, 160)}**")
            st.caption(f"Workspace `{ui.esc(workspace.id, 100)}` · {kind}")
        with top_right:
            st.markdown(
                ui.pill(owner.match_type.value.replace("_", " ").title(), "#155E56", "#E9F6F1"), unsafe_allow_html=True
            )
        st.markdown(
            f'<span class="gt-mono">{ui.esc(owner.resource_address, 240)}</span>',
            unsafe_allow_html=True,
        )
        details = []
        if workspace.environment:
            details.append(f"Environment: {workspace.environment}")
        if workspace.branch:
            details.append(f"Branch: {workspace.branch}")
        if owner.run and owner.run.actor:
            details.append(f"Run actor: {owner.run.actor}")
        if owner.run and owner.run.status:
            details.append(f"Run status: {owner.run.status}")
        if owner.state_version:
            details.append(f"State version: {owner.state_version.id}")
        if owner.last_seen_at:
            details.append(f"Last seen: {owner.last_seen_at.isoformat(timespec='seconds')}")
        st.caption(" · ".join(details))
        url = safe_url(workspace.source_url)
        if url:
            st.link_button("Open workspace in Scalr", url)
        st.markdown("**Evidence**")
        ui.evidence_chips(owner.evidence_ids, result=state.current_result())
        for limitation in owner.limitations:
            st.caption(f"Limitation: {limitation}")


def render() -> None:
    result = state.current_result()
    if result is None:
        ui.header("Lineage", "See which workspace owns the resource — and when that changed.", "")
        ui.empty_state("No investigation loaded", "Run a fixture case from Home or Investigate to populate this page.")
        return
    ui.header(
        "Lineage",
        f"{result.resource.name}",
        "Ownership is inferred only from exact identity matches. Repository proximity alone is a candidate, never an ownership claim.",
    )
    ui.fixture_banner(result.fixture, result.mode)
    summary_left, summary_right = st.columns([2, 1])
    with summary_left:
        st.markdown(ui.status_pill(result.status.value), unsafe_allow_html=True)
        st.markdown(f"#### {ui.esc(result.status_reason, 360)}")
        st.caption(f"Confidence rule: {result.confidence_rule}")
    with summary_right:
        ui.metric("Confidence", result.confidence.value, result.confidence_reason)

    with st.container(border=True):
        st.markdown("**Resource identity**")
        columns = st.columns(4)
        columns[0].metric("Region", result.resource.region or "unknown")
        columns[1].metric("Type", result.resource.resource_type)
        columns[2].metric("Status", result.resource.status or "unknown")
        columns[3].metric("Evidence", str(len(result.evidence)))
        st.code(result.resource.arn or result.resource.identity, language=None)

    ui.section(
        "Ownership", "Scalr resource usage provides the managing workspace; exact ARN matching links it to this Lambda."
    )
    if result.current_owners:
        st.markdown("**Current owners**")
        for owner in result.current_owners:
            _owner_card(owner, "current")
    else:
        ui.empty_state(
            "No current owner",
            "No active Scalr resource usage with an exact identity match was found in the checked sources.",
        )
    if result.historical_managers:
        st.markdown("**Historical managers**")
        for owner in result.historical_managers:
            _owner_card(owner, "historical")

    lineage = result.repository_lineage
    if lineage:
        ui.section(
            "Repository lineage",
            "The exact VCS revision from the Scalr run is verified against the local or GitLab commit.",
        )
        with st.container(border=True):
            left, right = st.columns([2, 1])
            with left:
                st.markdown(f"**{ui.esc(lineage.repository, 180)}**")
                st.caption(
                    f"Branch: {lineage.branch or 'unknown'} · Working directory: {lineage.working_directory or 'repository root'}"
                )
                st.code(lineage.vcs_revision or "No exact VCS revision", language=None)
            with right:
                if lineage.commit_verified:
                    st.markdown(ui.pill("Exact SHA verified", "#155E56", "#E9F6F1"), unsafe_allow_html=True)
                elif lineage.candidate_only:
                    st.markdown(ui.pill("Candidate only", "#6B4EFF", "#ECE8FF"), unsafe_allow_html=True)
                else:
                    st.markdown(ui.pill("Not verified", "#475467", "#EAECF0"), unsafe_allow_html=True)
            st.markdown("**Citations**")
            ui.evidence_chips(lineage.evidence_ids, result=result)
            commit = lineage.commit
            if commit:
                st.markdown("**Verified commit**")
                st.markdown(
                    f'<span class="gt-mono">{ui.esc(commit.sha, 64)}</span> · {ui.esc(commit.message, 300)} · '
                    f"{ui.esc(commit.author_name or 'unknown author', 100)}",
                    unsafe_allow_html=True,
                )
                if commit.committed_at:
                    st.caption(commit.committed_at.isoformat(timespec="seconds"))
            for label, matches in (
                ("File matches", lineage.file_matches),
                ("History matches", lineage.history_matches),
            ):
                if matches:
                    st.markdown(f"**{label}**")
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "Path": item.path,
                                    "Matched": item.matched_string,
                                    "Match": item.match_type.value,
                                    "Commit": item.commit_sha or "",
                                    "Line": item.line or "",
                                }
                                for item in matches
                            ]
                        ),
                        hide_index=True,
                        width="stretch",
                    )
            for limitation in lineage.limitations:
                st.caption(f"Limitation: {limitation}")

    if result.actors:
        ui.section(
            "Actors observed", "People and systems seen in state changes or audit events. Presence is not ownership."
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Source": actor.source.value,
                        "Identity type": actor.identity_type,
                        "Identifier": actor.identifier,
                        "Display name": actor.display_name or "",
                        "Observed": actor.timestamp.isoformat(timespec="seconds") if actor.timestamp else "",
                        "Evidence": actor.evidence_id,
                    }
                    for actor in result.actors
                ]
            ),
            hide_index=True,
            width="stretch",
        )

    ui.section("Recommendation")
    with st.container(border=True):
        st.markdown(f"**{ui.esc(result.recommendation.title, 220)}**")
        st.write(result.recommendation.explanation)
        if result.recommendation.blocked_adoption:
            st.error("Do not adopt or change this resource until the ownership conflict is resolved.")
        ui.evidence_chips(result.recommendation.evidence_ids, result=result)

    gaps = result.coverage_gaps()
    if gaps:
        ui.section("Coverage gaps", "A missing record is a visibility gap, not evidence that the event never happened.")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Source": gap.source,
                        "Status": gap.status.value,
                        "Required": gap.required,
                        "Records": gap.records,
                        "Error": gap.error or "",
                    }
                    for gap in gaps
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    if result.unresolved_questions:
        ui.section("Open questions")
        for question in result.unresolved_questions:
            st.markdown(f"- {question}")
    if result.limitations:
        with st.expander("Known limitations", expanded=False):
            for limitation in result.limitations:
                st.markdown(f"- {limitation}")
