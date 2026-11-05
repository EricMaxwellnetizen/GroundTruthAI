from __future__ import annotations

from groundtruth.services.freshness import EndpointContract
from groundtruth.services.freshness_agent import FreshnessAgent

CONTRACT = EndpointContract(
    connector="demo_api",
    operation="GET /things",
    docs_url="https://docs.example.com/things",
    checked_on="2026-01-01",
    deterministic_surface="groundtruth/connectors/demo.py",
)


def test_agent_records_baseline_then_detects_drift(tmp_path, settings) -> None:
    pages = {"text": "v1 docs"}
    agent = FreshnessAgent(tmp_path, settings, fetcher=lambda url: pages["text"])
    first = agent.run([CONTRACT])
    assert first.watches[0].changed is False
    assert (tmp_path / "freshness_baseline.json").exists()

    pages["text"] = "v2 docs with new required parameter"
    second = FreshnessAgent(tmp_path, settings, fetcher=lambda url: pages["text"]).run([CONTRACT])
    assert second.watches[0].changed is True
    assert (tmp_path / "contracts_override.json").exists()
    assert (tmp_path / "PATCH_PROPOSAL.md").exists()
    assert any("Auto-updated contract registry" in u for u in second.updates_applied)
    assert second.ai_used is False  # no model configured in test settings


def test_agent_survives_unreachable_docs(tmp_path, settings) -> None:
    def boom(url: str) -> str:
        raise OSError("offline")

    run = FreshnessAgent(tmp_path, settings, fetcher=boom).run([CONTRACT])
    assert run.watches[0].reachable is False
    assert run.watches[0].changed is False
