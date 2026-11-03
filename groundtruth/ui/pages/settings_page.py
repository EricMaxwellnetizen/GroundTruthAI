from __future__ import annotations

import pandas as pd
import streamlit as st

from groundtruth.config import Settings
from groundtruth.connectors import (
    AwsLambdaConnector,
    CloudTrailConnector,
    CloudWatchMetricsConnector,
    CloudWatchOmniConnector,
    FixtureCaseLoader,
    GitLabConnector,
    GitLocalConnector,
    ScalrConnector,
)
from groundtruth.exports.common import redact_text
from groundtruth.mcp import McpManager
from groundtruth.models.connector import ConnectionTest
from groundtruth.models.enums import ConnectorStatus
from groundtruth.ui import components as ui
from groundtruth.ui import state
from groundtruth.utils.redaction import redact_account_id, safe_text


def _test_key(name: str) -> str:
    return f"connection_test_{name}"


def _run_test(name: str, factory) -> None:
    with st.spinner(f"Testing {name}..."):
        try:
            outcome = factory()
        except Exception as exc:
            outcome = ConnectionTest(
                name=name,
                status=ConnectorStatus.FAILED,
                message=safe_text(f"{exc.__class__.__name__}: {exc}", limit=500),
            )
    st.session_state[_test_key(name)] = outcome


def _show_test(name: str) -> None:
    outcome = st.session_state.get(_test_key(name))
    if not isinstance(outcome, ConnectionTest):
        return
    text = f"{outcome.status.value} — {outcome.message}"
    if outcome.status in {ConnectorStatus.SUCCESS}:
        st.success(text)
    elif outcome.status in {ConnectorStatus.PARTIAL, ConnectorStatus.NOT_FOUND, ConnectorStatus.NOT_CONFIGURED}:
        st.warning(text)
    else:
        st.error(text)
    safe_details = {}
    for key, value in outcome.details.items():
        if key in {"account_id"}:
            safe_details[key] = redact_account_id(str(value))
        elif key in {"caller_arn", "arn"}:
            safe_details[key] = redact_text(str(value))
        elif key in {"region", "url", "status", "commit", "path", "workspace_count", "project", "server_count"}:
            safe_details[key] = redact_text(str(value))
    if safe_details:
        st.caption(" · ".join(f"{key}: {value}" for key, value in safe_details.items()))
    st.caption(f"Tested {outcome.tested_at.isoformat(timespec='seconds')}")


def _test_meta(settings: Settings) -> ConnectionTest:
    if not settings.ai_configured:
        return ConnectionTest(
            name="Meta Muse Spark",
            status=ConnectorStatus.NOT_CONFIGURED,
            message="Set MODEL_API_KEY and AI_ENABLED=true to test Muse Spark.",
        )
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.model_api_key, base_url=settings.meta_api_base_url, timeout=settings.request_timeout_seconds
    )
    response = client.chat.completions.create(
        model=settings.meta_model,
        messages=[{"role": "user", "content": "Reply with the single word OK."}],
        max_tokens=4,
        temperature=0,
    )
    content = (response.choices[0].message.content or "").strip()
    return ConnectionTest(
        name="Meta Muse Spark",
        status=ConnectorStatus.SUCCESS if content else ConnectorStatus.PARTIAL,
        message="Muse Spark responded to a minimal prompt." if content else "Muse Spark returned an empty response.",
        details={"model": settings.meta_model, "url": settings.meta_api_base_url},
    )


def _test_mcp(settings: Settings) -> ConnectionTest:
    manager = McpManager(settings)
    if not manager.enabled:
        return ConnectionTest(
            name="MCP",
            status=ConnectorStatus.NOT_CONFIGURED,
            message="No MCP servers configured. Set GROUNDTRUTH_MCP_SERVERS and GROUNDTRUTH_MCP_ALLOWLIST.",
        )
    manager.discover()
    summary = manager.summary()
    connected = int(summary["connected_servers"])
    return ConnectionTest(
        name="MCP",
        status=ConnectorStatus.SUCCESS if connected else ConnectorStatus.FAILED,
        message=f"{connected} of {summary['configured_servers']} server(s) connected; {summary['approved_tools']} tool(s) allowed.",
        details={"server_count": summary["configured_servers"]},
    )


def render() -> None:
    settings = state.settings()
    ui.header(
        "Settings & connections",
        "Evidence before confidence.",
        "Configuration comes from environment variables. Secrets are read locally and are never shown, logged, or exported. A successful test does not imply broad permissions.",
    )
    ui.fixture_banner(settings.mode == "fixture", settings.mode)
    st.info(
        "Live-mode claims require successful AWS Lambda and Scalr reads. Optional sources only affect coverage. "
        "Credentials stay in the process environment and are never persisted by GroundTruth."
    )

    ui.section("Runtime configuration", "Non-secret values only.")
    rows = [
        ("Mode", settings.mode),
        ("Database URL", settings.database_url),
        ("Fixture directory", str(settings.fixtures_dir)),
        ("AWS region", settings.aws_region),
        ("AWS credentials", "Configured" if settings.aws_configured else "Not configured"),
        ("Scalr base URL", settings.scalr_base_url or "Not configured"),
        ("Scalr token", "Configured" if settings.scalr_credentials_configured else "Not configured"),
        ("Scalr resource filter", settings.scalr_tf_resource_usage_filter or "Not configured"),
        ("Git repository", settings.git_repo_path or "Not configured"),
        ("GitLab base URL", settings.gitlab_base_url or "Not configured"),
        ("GitLab token", "Configured" if settings.gitlab_token else "Not configured"),
        ("Meta API base", settings.meta_api_base_url),
        ("Meta model", settings.meta_model),
        ("AI enabled", "Yes" if settings.ai_enabled else "No"),
        ("Redact account IDs", "Yes" if settings.redact_account_ids else "No"),
        ("Request timeout", f"{settings.request_timeout_seconds}s"),
        ("Max pages per source", str(settings.max_pages)),
        ("MCP servers", str(len(settings.mcp_servers))),
        ("MCP allowlist", ", ".join(settings.mcp_allowlist) or "Default deny"),
        ("Saved investigations", str(state.repository().count())),
    ]
    st.dataframe(pd.DataFrame(rows, columns=["Setting", "Value"]), hide_index=True, width="stretch")

    ui.section(
        "Connection tests",
        "Each test performs a real read-only call. Failures are reported honestly and never retried as writes.",
    )
    columns = st.columns(4)
    tests = [
        ("Fixture", "Fixture", lambda: FixtureCaseLoader(settings).test_connection()),
        ("AWS", "AWS Lambda", lambda: AwsLambdaConnector(settings).test_connection()),
        ("Scalr", "Scalr", lambda: ScalrConnector(settings).test_connection()),
        ("Git", "Local Git", lambda: GitLocalConnector(settings).test_connection()),
        ("GitLab", "GitLab", lambda: GitLabConnector(settings).test_connection()),
        (
            "CloudTrail",
            "CloudTrail",
            lambda: CloudTrailConnector(settings, region=settings.aws_region).test_connection(),
        ),
        (
            "CloudWatch",
            "CloudWatch",
            lambda: CloudWatchMetricsConnector(settings, region=settings.aws_region).test_connection(),
        ),
        ("Omni", "CloudWatch Omni", lambda: CloudWatchOmniConnector(settings).test_connection()),
        ("MCP", "MCP discovery", lambda: _test_mcp(settings)),
        ("Meta", "Meta Muse Spark", lambda: _test_meta(settings)),
    ]
    for index, (name, label, factory) in enumerate(tests):
        with columns[index % 4]:
            st.button(label, key=f"test_button_{name}", on_click=_run_test, args=(name, factory), width="stretch")
    for name, label, _factory in tests:
        with st.expander(label, expanded=False):
            _show_test(name)

    ui.section("Reload configuration")
    st.caption(
        "GroundTruth reads environment variables at process start. After changing .env or shell variables, reload the cached "
        "settings, orchestrator, repository, and AI client."
    )
    if st.button("Reload cached configuration", key="reload_settings"):
        st.cache_resource.clear()
        st.session_state["bundle"] = None
        st.rerun()

    ui.section("Environment variables")
    st.code(
        "\n".join(
            [
                "GROUNDTRUTH_MODE=fixture",
                "GROUNDTRUTH_DATABASE_URL=sqlite:///./groundtruth.db",
                "GROUNDTRUTH_REDACT_ACCOUNT_IDS=true",
                "AWS_REGION=ap-south-1",
                "AWS_ACCESS_KEY_ID=...",
                "AWS_SECRET_ACCESS_KEY=...",
                "SCALR_BASE_URL=https://your-account.scalr.io",
                "SCALR_API_TOKEN=...",
                "SCALR_TF_RESOURCE_USAGE_FILTER=...",
                "GIT_REPO_PATH=./demo-data/data-pipelines",
                "GITLAB_BASE_URL=https://gitlab.com",
                "GITLAB_TOKEN=...",
                "AI_ENABLED=false",
                "MODEL_API_KEY=...",
                "META_API_BASE_URL=https://api.meta.ai/v1",
                "META_MODEL=muse-spark-1.3",
                "GROUNDTRUTH_MCP_SERVERS=[]",
                "GROUNDTRUTH_MCP_ALLOWLIST=[]",
            ]
        ),
        language="bash",
    )
    st.caption("Never commit a populated .env file. The repository ships only .env.example.")
