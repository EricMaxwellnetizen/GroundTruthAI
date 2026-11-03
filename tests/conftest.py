from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from groundtruth.config import Settings  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROUNDTRUTH_DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


@pytest.fixture()
def settings(repo_root: Path) -> Settings:
    base = Settings.from_env()
    return replace(
        base,
        mode="fixture",
        database_url="sqlite:///:memory:",
        fixtures_dir=repo_root / "fixtures",
        demo_repo_path=repo_root / "demo-data" / "data-pipelines",
        git_repo_path=str(repo_root / "demo-data" / "data-pipelines"),
        gitlab_base_url="",
        gitlab_token="",
        aws_region="ap-south-1",
        scalr_base_url="",
        scalr_api_token="",
        scalr_tf_resource_usage_filter="",
        model_api_key="",
        ai_enabled=False,
        mcp_servers=[],
        mcp_allowlist=[],
        redact_account_ids=True,
        request_timeout_seconds=5,
    )
