from __future__ import annotations

import streamlit as st

from groundtruth.ui import components as ui
from groundtruth.ui import state
from groundtruth.ui.tasks import render_task_panel, start_fixture, start_live, task_running
from groundtruth.models.state_backup import StateBackupEvidence
from groundtruth.services.state_backup import StateBackupError, parse_state_backup


def _state_backup_panel() -> StateBackupEvidence | None:
    with st.expander("Existing Terraform state backup (optional)", expanded=False):
        st.caption(
            "Parsed in memory on this machine. Only Lambda identity and non-secret configuration fields are kept; "
            "raw state, outputs, variables, environment values and secrets are discarded and never sent to the model."
        )
        upload = st.file_uploader(
            "Upload a .tfstate or state JSON file",
            type=["json", "tfstate"],
            key="state_backup_upload",
        )
        parse_col, remove_col = st.columns(2)
        with parse_col:
            if st.button(
                "Parse state backup locally",
                key="parse_state_backup",
                disabled=upload is None,
                width="stretch",
            ):
                try:
                    parsed = parse_state_backup(upload.getvalue(), filename=upload.name)
                except StateBackupError as exc:
                    st.session_state["state_backup"] = None
                    st.session_state["state_backup_error"] = str(exc)
                else:
                    st.session_state["state_backup"] = parsed
                    st.session_state["state_backup_error"] = None
        with remove_col:
            if st.button("Remove parsed backup", key="remove_state_backup", width="stretch"):
                st.session_state["state_backup"] = None
                st.session_state["state_backup_error"] = None
        error = st.session_state.get("state_backup_error")
        if error:
            st.error(f"State backup rejected: {ui.esc(str(error), 300)}")
        backup = st.session_state.get("state_backup")
        if not isinstance(backup, StateBackupEvidence):
            return None
        st.success(
            f"Parsed {ui.esc(backup.filename, 160)} locally — {len(backup.matches)} Lambda resource(s), "
            f"state version {backup.state_version}, serial {backup.serial if backup.serial is not None else 'unknown'}."
        )
        st.caption(f"SHA-256 {backup.sha256[:16]}… · user-supplied evidence; not live-verified and not persisted.")
        if backup.matches:
            st.dataframe(
                [
                    {
                        "address": match.address,
                        "function": match.function_name or "",
                        "arn": match.arn or "",
                    }
                    for match in backup.matches[:10]
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.warning("No managed aws_lambda_function resource was found in this state file.")
        st.caption("The backup can support a candidate lineage, but it cannot override exact live evidence.")
        return backup


def _fixture_form() -> None:
    cases = state.orchestrator().list_fixture_cases()
    if not cases:
        ui.empty_state("No fixture cases found", "Check the fixtures/cases directory and GROUNDTRUTH_FIXTURES_DIR.")
        return
    labels = {case["case_id"]: f"{case['label']} — {case.get('expected_status', '')}" for case in cases}
    case_id = st.selectbox(
        "Fixture case",
        options=[case["case_id"] for case in cases],
        format_func=lambda value: labels.get(value, value),
        key="fixture_case_select",
    )
    selected = next(case for case in cases if case["case_id"] == case_id)
    st.caption(selected.get("summary") or "")
    meta_left, meta_right = st.columns([1, 1])
    with meta_left:
        st.markdown(ui.status_pill(str(selected.get("expected_status") or "")), unsafe_allow_html=True)
    with meta_right:
        st.caption(f"Expected confidence: {selected.get('expected_confidence') or 'unknown'}")
    st.button(
        "Run fixture investigation",
        type="primary",
        width="stretch",
        disabled=task_running(),
        on_click=start_fixture,
        args=(case_id, selected["label"]),
    )


def _live_form() -> None:
    settings = state.settings()
    st.markdown("**Resource identity**")
    identifier = st.text_input(
        "Lambda ARN or function name",
        placeholder="arn:aws:lambda:ap-south-1:123456789012:function:orders-transformer",
        key="live_identifier",
    )
    col1, col2 = st.columns(2)
    with col1:
        region = st.text_input("Region", value=settings.aws_region, key="live_region")
    with col2:
        account_id = st.text_input(
            "Account ID (optional when using a full ARN)",
            placeholder="123456789012",
            key="live_account",
        )
    with st.expander("Time window and sources", expanded=True):
        window1, window2 = st.columns(2)
        with window1:
            cloudtrail_days = st.slider(
                "CloudTrail lookback (days)",
                min_value=1,
                max_value=90,
                value=min(settings.cloudtrail_lookback_days, 90),
                key="live_cloudtrail_days",
                help="CloudTrail Event History is a 90-day regional window, not a complete archive.",
            )
        with window2:
            cloudwatch_days = st.slider(
                "CloudWatch lookback (days)",
                min_value=1,
                max_value=90,
                value=min(settings.cloudwatch_lookback_days, 90),
                key="live_cloudwatch_days",
            )
        st.caption(
            "AWS Lambda and Scalr are required for an ownership claim. Optional sources affect coverage, not authorization."
        )
        st.checkbox("AWS Lambda (required)", value=True, disabled=True, key="src_aws")
        st.checkbox("Scalr (required)", value=True, disabled=True, key="src_scalr")
        optional = st.multiselect(
            "Optional sources",
            options=["Git / repository", "CloudTrail", "CloudWatch", "CloudWatch Omni"],
            default=["Git / repository", "CloudTrail", "CloudWatch", "CloudWatch Omni"],
            key="live_optional_sources",
        )
    sources = {"aws", "scalr"}
    mapping = {
        "Git / repository": "git",
        "CloudTrail": "cloudtrail",
        "CloudWatch": "cloudwatch",
        "CloudWatch Omni": "omni",
    }
    sources.update(mapping[item] for item in optional)
    state_backup = _state_backup_panel()
    st.button(
        "Run live investigation",
        type="primary",
        width="stretch",
        disabled=task_running(),
        on_click=start_live,
        args=(identifier.strip(),),
        kwargs={
            "region": region.strip(),
            "account_id": account_id.strip(),
            "sources": sources,
            "cloudtrail_lookback_days": cloudtrail_days,
            "cloudwatch_lookback_days": cloudwatch_days,
            "state_backup": state_backup,
        },
    )
    if not settings.scalr_configured:
        st.warning(
            "Scalr is not fully configured; live runs will return INSUFFICIENT_ACCESS rather than guessing an owner."
        )
    if not settings.aws_configured:
        st.warning("AWS region is not configured. Set AWS_REGION or enter a region.")


def render() -> None:
    settings = state.settings()
    ui.header(
        "Investigate",
        "Trace one Lambda from cloud identity to managing workspace.",
        "Fixture mode works offline and is the verified demo path. Live mode uses read-only connectors and labels every gap.",
    )
    ui.fixture_banner(settings.mode == "fixture", settings.mode)
    mode = st.radio(
        "Investigation source",
        options=["Fixture", "Live"],
        horizontal=True,
        index=0 if settings.mode == "fixture" else 1,
        key="investigate_mode",
    )
    if mode == "Fixture":
        _fixture_form()
    else:
        _live_form()

    render_task_panel()

    result = state.current_result()
    if result is not None and not task_running():
        ui.section("Current result", "The latest completed investigation is available across all pages.")
        with st.container(border=True):
            top_left, top_right = st.columns([3, 1])
            with top_left:
                st.markdown(f"**{ui.esc(result.resource.name, 160)}**")
                st.caption(result.resource.arn or "No ARN recorded")
            with top_right:
                st.markdown(ui.status_pill(result.status.value), unsafe_allow_html=True)
                st.markdown(ui.confidence_pill(result.confidence.value), unsafe_allow_html=True)
            st.caption(result.status_reason)
            st.markdown(
                f"`{ui.esc(result.investigation_id, 80)}` · {len(result.evidence)} evidence records · {len(result.graph.nodes)} graph nodes"
            )
            if result.recommendation.blocked_adoption:
                st.warning(
                    "Adoption is blocked by this investigation. Resolve the conflict before changing the resource."
                )
