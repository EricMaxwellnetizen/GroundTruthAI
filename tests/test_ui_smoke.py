from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

from groundtruth.ai import AIExplainService  # noqa: E402
from groundtruth.config import Settings  # noqa: E402
from groundtruth.exports import build_evidence_bundle  # noqa: E402
from groundtruth.services.orchestrator import InvestigationOrchestrator  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    "Home / Overview",
    "Investigate",
    "Resource inventory",
    "Lineage overview",
    "Evidence graph",
    "Timeline",
    "Dependencies & activity",
    "AI explanation",
    "Evidence report",
    "Settings / connections",
]


def test_empty_pages_render_without_exceptions() -> None:
    app = AppTest.from_file(str(ROOT / "groundtruth" / "app.py"), default_timeout=90)
    app.run()
    for page in PAGES:
        app.session_state["nav"] = page
        app.run()
        assert not app.exception, f"{page}: {[str(item.value) for item in app.exception]}"


def test_pages_render_with_a_fixture_result() -> None:
    settings = Settings.from_env()
    result = InvestigationOrchestrator(settings).run_fixture("E_current_owner")
    result.ai_explanation = AIExplainService(settings).explain(result)
    bundle = build_evidence_bundle(result, redact=True)
    app = AppTest.from_file(str(ROOT / "groundtruth" / "app.py"), default_timeout=90)
    app.run()
    app.session_state["result"] = result
    app.session_state["bundle"] = bundle
    app.session_state["stored_id"] = result.investigation_id
    for page in PAGES:
        app.session_state["nav"] = page
        app.run()
        assert not app.exception, f"{page}: {[str(item.value) for item in app.exception]}"
    assert app.session_state["result"].status.value == "CURRENT_OWNER_FOUND"
