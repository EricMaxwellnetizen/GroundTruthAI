from __future__ import annotations

from groundtruth.services.adoption import build_adoption_proposal
from groundtruth.services.orchestrator import InvestigationOrchestrator


def test_adoption_preview_for_unattributed_function(settings) -> None:
    result = InvestigationOrchestrator(settings).run_fixture("F_unattributed")
    proposal = build_adoption_proposal(result)
    assert proposal.eligible is True
    assert "aws_lambda_function" in proposal.hcl
    assert "import {" in proposal.hcl
    assert "invoice-pdf-renderer" in proposal.hcl
    assert proposal.checklist
    assert any("never runs" in w for w in proposal.warnings)


def test_adoption_blocked_for_duplicate_owners(settings) -> None:
    result = InvestigationOrchestrator(settings).run_fixture("B_multiple_active_owners")
    proposal = build_adoption_proposal(result)
    assert proposal.eligible is False
    assert proposal.hcl == ""
    assert proposal.blocked_reason


def test_adoption_blocked_for_ambiguous_identity(settings) -> None:
    result = InvestigationOrchestrator(settings).run_fixture("G_identity_ambiguous")
    proposal = build_adoption_proposal(result)
    assert proposal.eligible is False


def test_adoption_warns_when_owner_already_exists(settings) -> None:
    result = InvestigationOrchestrator(settings).run_fixture("E_current_owner")
    proposal = build_adoption_proposal(result)
    assert proposal.eligible is True
    assert any("already managed" in w for w in proposal.warnings)
