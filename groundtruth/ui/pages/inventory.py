from __future__ import annotations

import pandas as pd
import streamlit as st

from groundtruth.connectors import FixtureCaseLoader
from groundtruth.ui import components as ui
from groundtruth.ui import state
from groundtruth.ui.tasks import start_fixture


def _open_case(case_id: str, label: str) -> None:
    start_fixture(case_id, label)
    st.session_state["nav"] = "Investigate"


def render() -> None:
    settings = state.settings()
    ui.header(
        "Inventory",
        "Lambdas discovered in the checked sources.",
        "Fixture mode shows synthetic Lambda functions from the case pack. Live inventory uses Lambda ListFunctions with read-only credentials.",
    )
    ui.fixture_banner(settings.mode == "fixture", settings.mode)
    resources = state.orchestrator().fixture_inventory()
    cases = state.orchestrator().list_fixture_cases()
    loader = FixtureCaseLoader(settings)
    case_resources: dict[str, str] = {}
    for case in cases:
        try:
            loaded = loader.load(case["case_id"])
        except (OSError, ValueError):
            continue
        case_resources[loaded.resource.identity] = case["case_id"]

    search = st.text_input("Filter by function name, ARN, tag, or region", key="inventory_filter")
    col1, col2 = st.columns(2)
    with col1:
        regions = sorted({resource.region for resource in resources if resource.region})
        region = st.selectbox("Region", ["All"] + regions, key="inventory_region")
    with col2:
        states = sorted({resource.status for resource in resources if resource.status})
        status = st.selectbox("Status", ["All"] + states, key="inventory_status")

    filtered = []
    for resource in resources:
        haystack = " ".join(
            [resource.name, resource.arn or "", resource.region, resource.status or ""]
            + [f"{key}={value}" for key, value in resource.tags.items()]
        ).lower()
        if search and search.lower() not in haystack:
            continue
        if region != "All" and resource.region != region:
            continue
        if status != "All" and resource.status != status:
            continue
        filtered.append(resource)

    current = state.current_result()
    rows = []
    for resource in filtered:
        rows.append(
            {
                "Name": resource.name,
                "Type": resource.resource_type,
                "Region": resource.region,
                "Status": resource.status or "",
                "Account": resource.account_id,
                "Investigation": "Current result"
                if current and current.resource.identity == resource.identity
                else "Not investigated",
                "ARN": resource.arn or "",
            }
        )
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        ui.empty_state("No resources match", "Clear the filters or switch back to the fixture case list.")

    if len(filtered) == 1:
        resource = filtered[0]
        case_id = case_resources.get(resource.identity)
        with st.container(border=True):
            st.markdown(f"**{ui.esc(resource.name, 160)}**")
            st.caption(resource.arn or "No ARN")
            st.markdown(
                " ".join(
                    f'<span class="gt-chip">{ui.esc(key, 60)}={ui.esc(value, 120)}</span>'
                    for key, value in sorted(resource.tags.items())
                ),
                unsafe_allow_html=True,
            )
            if case_id:
                label = next((case["label"] for case in cases if case["case_id"] == case_id), case_id)
                st.button(
                    "Investigate this resource",
                    type="primary",
                    on_click=_open_case,
                    args=(case_id, label),
                )

    ui.section("Fixture cases", "Each case is a versioned synthetic scenario with an expected terminal status.")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Case": case["case_id"],
                    "Scenario": case["label"],
                    "Expected status": case.get("expected_status"),
                    "Expected confidence": case.get("expected_confidence"),
                    "Mode": "Fixture",
                }
                for case in cases
            ]
        ),
        hide_index=True,
        width="stretch",
    )
