from __future__ import annotations

import pytest

from groundtruth.exports import build_evidence_bundle
from groundtruth.services.orchestrator import InvestigationOrchestrator
from groundtruth.storage import SqliteInvestigationRepository


def _bundle(settings):
    result = InvestigationOrchestrator(settings).run_fixture("E_current_owner")
    return build_evidence_bundle(result, redact=True)


def test_memory_repository_crud(settings) -> None:
    repo = SqliteInvestigationRepository("sqlite:///:memory:")
    bundle = _bundle(settings)
    stored = repo.save(bundle)
    assert stored.investigation_id == bundle.investigation_id
    fetched = repo.get(bundle.investigation_id)
    assert fetched is not None
    assert fetched.status == "CURRENT_OWNER_FOUND"
    assert fetched.report["investigation_id"] == bundle.investigation_id
    assert repo.count() == 1
    assert [item.investigation_id for item in repo.list(limit=5)] == [bundle.investigation_id]
    assert repo.delete(bundle.investigation_id) is True
    assert repo.get(bundle.investigation_id) is None
    assert repo.delete("missing") is False


def test_file_repository_persists_across_instances(settings, tmp_path) -> None:
    database = tmp_path / "nested" / "groundtruth.db"
    url = f"sqlite:///{database.as_posix()}"
    first = SqliteInvestigationRepository(url)
    bundle = _bundle(settings)
    first.save(bundle)
    second = SqliteInvestigationRepository(url)
    fetched = second.get(bundle.investigation_id)
    assert fetched is not None
    assert fetched.checksum == (bundle.integrity.checksum if bundle.integrity else None)
    assert database.exists()


def test_preferences_and_secret_rejection(settings) -> None:
    repo = SqliteInvestigationRepository("sqlite:///:memory:")
    repo.set_preference("last_page", "Timeline")
    assert repo.get_preference("last_page") == "Timeline"
    repo.set_preference("last_page", "Report")
    assert repo.get_preference("last_page") == "Report"
    assert repo.get_preference("missing", "fallback") == "fallback"
    with pytest.raises(ValueError):
        repo.set_preference("SCALR_API_TOKEN", "do-not-store")
    with pytest.raises(ValueError):
        repo.set_preference("model_api_key", "do-not-store")


def test_rejects_non_sqlite_url(settings) -> None:
    with pytest.raises(ValueError):
        SqliteInvestigationRepository("postgresql://localhost/groundtruth")
