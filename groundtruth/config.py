from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _text(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _json(name: str, default: Any) -> Any:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _safe_http_url(value: str) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


@dataclass(frozen=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    app_name: str = "GroundTruth"
    tagline: str = "Find the owner before you touch the resource."
    version: str = "1.0.0"
    mode: str = "fixture"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./groundtruth.db"
    max_scan_seconds: int = 180
    max_pages: int = 20
    page_size: int = 100
    request_timeout_seconds: int = 20
    max_retries: int = 3
    redact_account_ids: bool = True
    demo_repo_path: Path = PROJECT_ROOT / "demo-data" / "data-pipelines"
    fixtures_dir: Path = PROJECT_ROOT / "fixtures"
    aws_profile: str = ""
    aws_region: str = "ap-south-1"
    aws_default_region: str = "ap-south-1"
    scalr_base_url: str = ""
    scalr_api_token: str = ""
    scalr_tf_resource_usage_filter: str = ""
    scalr_page_size: int = 100
    git_repo_path: str = ""
    gitlab_base_url: str = "https://gitlab.com"
    gitlab_project_id: str = ""
    gitlab_token: str = ""
    model_api_key: str = ""
    meta_api_base_url: str = "https://api.meta.ai/v1"
    meta_model: str = "muse-spark-1.3"
    ai_enabled: bool = False
    cloudwatch_omni_url: str = ""
    cloudwatch_omni_space: str = ""
    cloudtrail_lookback_days: int = 90
    cloudwatch_lookback_days: int = 14
    cloudwatch_period_seconds: int = 300
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    mcp_allowlist: list[str] = field(default_factory=list)
    ui_sync_mode: bool = False
    debug: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        root = PROJECT_ROOT
        mode = _text("GROUNDTRUTH_MODE", "fixture").lower()
        if mode not in {"fixture", "live"}:
            mode = "fixture"
        region = _text("AWS_REGION", _text("AWS_DEFAULT_REGION", "ap-south-1"))
        scalr_base = _text("SCALR_BASE_URL").rstrip("/")
        git_path = _text("GIT_REPO_PATH")
        return cls(
            project_root=root,
            mode=mode,
            log_level=_text("GROUNDTRUTH_LOG_LEVEL", "INFO").upper(),
            database_url=_text("GROUNDTRUTH_DATABASE_URL", "sqlite:///./groundtruth.db"),
            max_scan_seconds=_int("GROUNDTRUTH_MAX_SCAN_SECONDS", 180),
            max_pages=_int("GROUNDTRUTH_MAX_PAGES", 20),
            page_size=_int("GROUNDTRUTH_PAGE_SIZE", 100),
            request_timeout_seconds=_int("GROUNDTRUTH_REQUEST_TIMEOUT_SECONDS", 20),
            max_retries=_int("GROUNDTRUTH_MAX_RETRIES", 3),
            redact_account_ids=_bool("GROUNDTRUTH_REDACT_ACCOUNT_IDS", True),
            demo_repo_path=Path(_text("GROUNDTRUTH_DEMO_REPO_PATH", str(root / "demo-data" / "data-pipelines"))),
            fixtures_dir=Path(_text("GROUNDTRUTH_FIXTURES_DIR", str(root / "fixtures"))),
            aws_profile=_text("AWS_PROFILE"),
            aws_region=region,
            aws_default_region=region,
            scalr_base_url=scalr_base if _safe_http_url(scalr_base) else "",
            scalr_api_token=_text("SCALR_API_TOKEN"),
            scalr_tf_resource_usage_filter=_text("SCALR_TF_RESOURCE_USAGE_FILTER"),
            scalr_page_size=_int("SCALR_PAGE_SIZE", 100),
            git_repo_path=str(Path(git_path).expanduser()) if git_path else "",
            gitlab_base_url=_text("GITLAB_BASE_URL", "https://gitlab.com").rstrip("/"),
            gitlab_project_id=_text("GITLAB_PROJECT_ID"),
            gitlab_token=_text("GITLAB_TOKEN"),
            model_api_key=_text("MODEL_API_KEY"),
            meta_api_base_url=_text("META_API_BASE_URL", "https://api.meta.ai/v1").rstrip("/"),
            meta_model=_text("META_MODEL", "muse-spark-1.3"),
            ai_enabled=_bool("AI_ENABLED", False),
            cloudwatch_omni_url=_text("CLOUDWATCH_OMNI_URL"),
            cloudwatch_omni_space=_text("CLOUDWATCH_OMNI_SPACE"),
            cloudtrail_lookback_days=max(1, min(_int("GROUNDTRUTH_CLOUDTRAIL_LOOKBACK_DAYS", 90), 90)),
            cloudwatch_lookback_days=max(1, _int("GROUNDTRUTH_CLOUDWATCH_LOOKBACK_DAYS", 14)),
            cloudwatch_period_seconds=max(60, _int("GROUNDTRUTH_CLOUDWATCH_PERIOD_SECONDS", 300)),
            mcp_servers=_json("GROUNDTRUTH_MCP_SERVERS", []),
            mcp_allowlist=[item.strip() for item in _text("GROUNDTRUTH_MCP_ALLOWLIST").split(",") if item.strip()],
            ui_sync_mode=_bool("GROUNDTRUTH_UI_SYNC", False),
            debug=_bool("GROUNDTRUTH_DEBUG", False),
        )

    @property
    def scalr_configured(self) -> bool:
        return bool(self.scalr_base_url and self.scalr_api_token and self.scalr_tf_resource_usage_filter)

    @property
    def scalr_credentials_configured(self) -> bool:
        return bool(self.scalr_base_url and self.scalr_api_token)

    @property
    def ai_configured(self) -> bool:
        return bool(self.ai_enabled and self.model_api_key)

    @property
    def git_configured(self) -> bool:
        return bool(self.git_repo_path)

    @property
    def gitlab_configured(self) -> bool:
        return bool(self.gitlab_project_id and self.gitlab_token)

    @property
    def aws_configured(self) -> bool:
        return bool(self.aws_region)

    @property
    def omni_configured(self) -> bool:
        return _safe_http_url(self.cloudwatch_omni_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
