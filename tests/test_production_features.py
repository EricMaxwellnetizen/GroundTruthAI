from __future__ import annotations

from datetime import datetime, timezone

from groundtruth.services.actions import ActionExecutor, ActionKind, plan_action
from groundtruth.services.automation import AutomationPolicy, run_automation, scan_attention
from groundtruth.services.credentials import CredentialVault, mask_value
from groundtruth.services.freshness import EndpointContract, check_freshness
from groundtruth.services.orchestrator import InvestigationOrchestrator


def test_credential_vault_writes_env_and_backup(tmp_path) -> None:
    vault = CredentialVault(tmp_path)
    vault.save(
        {"GROUNDTRUTH_MODE": "live", "AWS_REGION": "eu-west-1", "SCALR_API_TOKEN": "tok-secret-1234", "BOGUS": "x"}
    )
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    backup_text = (tmp_path / ".groundtruth" / "credentials.backup.env").read_text(encoding="utf-8")
    assert "GROUNDTRUTH_MODE=live" in env_text
    assert env_text == backup_text
    assert "BOGUS" not in env_text
    status = vault.status()
    assert status["SCALR_API_TOKEN"] == "••••1234"
    assert "tok-secret-1234" not in str(status)
    assert mask_value("") == ""


def test_delete_blocked_for_managed_function(settings) -> None:
    result = InvestigationOrchestrator(settings).run_fixture("E_current_owner")
    plan = plan_action(result, ActionKind.DELETE)
    assert plan.eligible is False


def test_action_requires_typed_confirmation(settings, tmp_path) -> None:
    result = InvestigationOrchestrator(settings).run_fixture("F_unattributed")
    plan = plan_action(result, ActionKind.DELETE)
    assert plan.eligible is True
    executor = ActionExecutor(tmp_path / "audit.jsonl")
    rejected = executor.execute(plan, mode="fixture", confirmation="wrong-name")
    assert rejected.outcome == "rejected"
    executed = executor.execute(plan, mode="fixture", confirmation="invoice-pdf-renderer")
    assert executed.outcome == "executed"
    assert len(executor.audit()) == 2


def test_automation_prepares_historical_reattribution_only(settings, tmp_path) -> None:
    orchestrator = InvestigationOrchestrator(settings)
    results = [orchestrator.run_fixture(case["case_id"]) for case in orchestrator.list_fixture_cases()]
    attention = scan_attention(results)
    names = {item.function_name for item in attention}
    assert "orders-transformer" in names  # historical (A) — appears once after dedupe by run order
    executor = ActionExecutor(tmp_path / "audit.jsonl")
    outcomes = run_automation(results, AutomationPolicy(enabled=True), executor)
    assert outcomes
    assert all(o["outcome"] in {"executed", "queued", "plan_only"} for o in outcomes)
    disabled = run_automation(results, AutomationPolicy(enabled=False), executor)
    assert all(o["outcome"] == "queued" for o in disabled)


def test_freshness_flags_stale_contracts() -> None:
    contracts = [
        EndpointContract(
            connector="x",
            operation="Op",
            docs_url="https://example.com",
            checked_on="2026-01-01",
            deterministic_surface="f.py",
        )
    ]
    report = check_freshness(interval_days=30, now=datetime(2026, 11, 5, tzinfo=timezone.utc), contracts=contracts)
    assert report.items[0].state == "stale"
    assert "x" in report.ai_review_prompt
