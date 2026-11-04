from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any

import streamlit as st

from groundtruth.ai import AIExplainService
from groundtruth.config import Settings
from groundtruth.exports import build_evidence_bundle
from groundtruth.models.state_backup import StateBackupEvidence
from groundtruth.services.orchestrator import InvestigationOrchestrator
from groundtruth.storage import SqliteInvestigationRepository
from groundtruth.ui import state
from groundtruth.utils.redaction import safe_text

STAGES: list[tuple[str, str]] = [
    ("fixture", "Fixture sources"),
    ("state_backup", "Terraform state backup"),
    ("aws_lambda", "AWS Lambda"),
    ("scalr", "Scalr resource usage"),
    ("git", "Git / repository"),
    ("cloudtrail", "CloudTrail events"),
    ("cloudwatch", "CloudWatch metrics"),
    ("cloudwatch_omni", "CloudWatch Omni"),
    ("correlation", "Deterministic correlation"),
    ("ai", "Muse Spark explanation"),
    ("export", "Evidence export"),
]
STAGE_INDEX = {key: index for index, (key, _) in enumerate(STAGES)}


def _stage_list() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "label": label,
            "status": "pending",
            "detail": "",
            "updated_at": None,
        }
        for key, label in STAGES
    ]


def _new_task(kind: str, title: str, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": f"task_{uuid.uuid4().hex[:12]}",
        "kind": kind,
        "title": title,
        "params": params,
        "status": "running",
        "stages": _stage_list(),
        "result": None,
        "explanation": None,
        "bundle": None,
        "error": None,
        "cancel_requested": False,
        "adopted": False,
        "started_at": datetime.now(timezone.utc),
        "finished_at": None,
    }


def _update_stage(task: dict[str, Any], key: str, status: str, detail: str | None = None) -> None:
    for stage in task["stages"]:
        if stage["key"] == key:
            stage["status"] = status
            if detail:
                stage["detail"] = safe_text(detail, limit=500)
            stage["updated_at"] = datetime.now(timezone.utc).isoformat()
            return


def _progress_callback(task: dict[str, Any]):
    def update(stage: str, status: str, detail: str | None = None) -> None:
        _update_stage(task, stage, status, detail)

    return update


def start_fixture(case_id: str, label: str) -> dict[str, Any]:
    task = _new_task("fixture", f"Fixture investigation: {label}", {"case_id": case_id})
    _update_stage(task, "fixture", "running", "Loading synthetic fixture case.")
    st.session_state["task"] = task
    thread = threading.Thread(target=_run_fixture, args=(task, case_id), daemon=True)
    thread.start()
    return task


def start_live(
    identifier: str,
    *,
    region: str,
    account_id: str,
    sources: set[str],
    cloudtrail_lookback_days: int,
    cloudwatch_lookback_days: int,
    state_backup: StateBackupEvidence | None = None,
) -> dict[str, Any]:
    task = _new_task(
        "live",
        f"Live investigation: {identifier}",
        {
            "identifier": identifier,
            "region": region,
            "account_id": account_id,
            "sources": sorted(sources),
            "cloudtrail_lookback_days": cloudtrail_lookback_days,
            "cloudwatch_lookback_days": cloudwatch_lookback_days,
            "state_backup_filename": state_backup.filename if state_backup else None,
        },
    )
    _update_stage(task, "fixture", "skipped", "Fixture mode not used for a live investigation.")
    st.session_state["task"] = task
    thread = threading.Thread(
        target=_run_live,
        args=(
            task,
            identifier,
            region,
            account_id,
            sources,
            cloudtrail_lookback_days,
            cloudwatch_lookback_days,
            state_backup,
        ),
        daemon=True,
    )
    thread.start()
    return task


def _finish_task(task: dict[str, Any], result: Any, settings: Settings) -> None:
    task["result"] = result
    task["explanation"] = result.ai_explanation
    task["bundle"] = build_evidence_bundle(result, redact=settings.redact_account_ids)
    task["status"] = "done"
    task["finished_at"] = datetime.now(timezone.utc).isoformat()


def _run_fixture(task: dict[str, Any], case_id: str) -> None:
    settings = state.settings()
    try:
        _update_stage(task, "state_backup", "skipped", "State backup upload applies to live investigations.")
        orchestrator = InvestigationOrchestrator(settings)
        result = orchestrator.run_fixture(case_id, progress=_progress_callback(task))
        if task["cancel_requested"]:
            task["status"] = "cancelled"
            task["finished_at"] = datetime.now(timezone.utc).isoformat()
            return
        _update_stage(task, "ai", "running", "Generating a grounded explanation.")
        explanation = AIExplainService(settings).explain(result)
        result.ai_explanation = explanation
        _update_stage(task, "ai", "done", f"Explanation source: {explanation.generated_by}.")
        if task["cancel_requested"]:
            task["status"] = "cancelled"
            task["finished_at"] = datetime.now(timezone.utc).isoformat()
            return
        _update_stage(task, "export", "running", "Building the redacted evidence bundle.")
        bundle = build_evidence_bundle(result, redact=settings.redact_account_ids)
        SqliteInvestigationRepository(settings.database_url).save(bundle)
        _update_stage(
            task,
            "export",
            "done",
            f"Checksum {bundle.integrity.checksum[:16]}…" if bundle.integrity else "Export complete.",
        )
        _finish_task(task, result, settings)
    except Exception as exc:
        task["status"] = "failed"
        task["error"] = safe_text(f"{exc.__class__.__name__}: {exc}", limit=800)
        task["finished_at"] = datetime.now(timezone.utc).isoformat()
        for stage in task["stages"]:
            if stage["status"] == "running":
                stage["status"] = "error"


def _run_live(
    task: dict[str, Any],
    identifier: str,
    region: str,
    account_id: str,
    sources: set[str],
    cloudtrail_lookback_days: int,
    cloudwatch_lookback_days: int,
    state_backup: StateBackupEvidence | None = None,
) -> None:
    settings = state.settings()
    try:
        orchestrator = InvestigationOrchestrator(settings)
        if state_backup is None:
            _update_stage(task, "state_backup", "skipped", "No state backup supplied.")
        else:
            _update_stage(
                task,
                "state_backup",
                "done",
                f"Parsed {state_backup.filename} locally; {len(state_backup.matches)} Lambda resource(s) found.",
            )
        result = orchestrator.run_live(
            identifier,
            region=region,
            account_id=account_id,
            progress=_progress_callback(task),
            sources=sources,
            cloudtrail_lookback_days=cloudtrail_lookback_days,
            cloudwatch_lookback_days=cloudwatch_lookback_days,
            state_backup=state_backup,
        )
        if task["cancel_requested"]:
            task["status"] = "cancelled"
            task["finished_at"] = datetime.now(timezone.utc).isoformat()
            return
        _update_stage(task, "ai", "running", "Generating a grounded explanation.")
        explanation = AIExplainService(settings).explain(result)
        result.ai_explanation = explanation
        _update_stage(task, "ai", "done", f"Explanation source: {explanation.generated_by}.")
        _update_stage(task, "export", "running", "Building the redacted evidence bundle.")
        bundle = build_evidence_bundle(result, redact=settings.redact_account_ids)
        SqliteInvestigationRepository(settings.database_url).save(bundle)
        _update_stage(
            task,
            "export",
            "done",
            f"Checksum {bundle.integrity.checksum[:16]}…" if bundle.integrity else "Export complete.",
        )
        _finish_task(task, result, settings)
    except Exception as exc:
        task["status"] = "failed"
        task["error"] = safe_text(f"{exc.__class__.__name__}: {exc}", limit=800)
        task["finished_at"] = datetime.now(timezone.utc).isoformat()
        for stage in task["stages"]:
            if stage["status"] == "running":
                stage["status"] = "error"


def _stage_line(stage: dict[str, Any]) -> str:
    status = stage["status"]
    marker = {
        "done": "DONE",
        "running": "RUN",
        "error": "ERR",
        "skipped": "SKIP",
        "pending": "WAIT",
    }.get(status, status.upper())
    detail = f" — {stage['detail']}" if stage.get("detail") else ""
    return f"`{marker}` **{stage['label']}**{detail}"


def render_task_panel() -> None:
    task = st.session_state.get("task")
    if not task:
        return

    @st.fragment(run_every=1.0 if task.get("status") == "running" else None)
    def panel() -> None:
        current = st.session_state.get("task")
        if not current:
            return
        status = current.get("status")
        if status == "running":
            done = len([item for item in current["stages"] if item["status"] in {"done", "skipped", "error"}])
            st.progress(
                done / max(1, len(current["stages"])), text=f"{done} of {len(current['stages'])} stages settled"
            )
        if status == "done" and not current.get("adopted"):
            current["adopted"] = True
            result = current.get("result")
            if result is None:
                st.error("The investigation completed without a result object.")
                return
            state.adopt_result(result, persist=False)
            st.session_state["task"] = current
            st.rerun(scope="app")
        with st.container(border=True):
            st.markdown(f"**{current['title']}**")
            for stage in current["stages"]:
                st.markdown(_stage_line(stage))
            if status == "running":
                if current.get("cancel_requested"):
                    st.warning(
                        "Cancellation requested. The current read-only source call will finish before the task stops."
                    )
                else:
                    if st.button("Cancel task", key=f"cancel_{current['task_id']}"):
                        current["cancel_requested"] = True
                        st.rerun(scope="fragment")
            elif status == "done":
                st.success("Investigation complete. Open Lineage overview, AI explanation, or Evidence report.")
            elif status == "cancelled":
                st.warning("Task cancelled. No new investigation result was saved.")
            elif status == "failed":
                st.error(f"Investigation failed: {current.get('error') or 'unknown error'}")

    panel()


def task_running() -> bool:
    task = st.session_state.get("task")
    return bool(task and task.get("status") == "running")
