from __future__ import annotations

import re
from urllib.parse import quote, urlparse

_COMMIT_SHA = re.compile(r"^[0-9a-f]{7,40}$")


def safe_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return url


def build_scalr_url(base_url: str, workspace_id: str | None = None, run_id: str | None = None) -> str | None:
    if not safe_url(base_url) or not base_url:
        return None
    base = base_url.rstrip("/")
    if workspace_id:
        return f"{base}/workspaces/{quote(str(workspace_id), safe='')}"
    if run_id:
        return f"{base}/runs/{quote(str(run_id), safe='')}"
    return base


def build_gitlab_url(
    base_url: str, project: str | None, commit_sha: str | None = None, path: str | None = None
) -> str | None:
    if not safe_url(base_url) or not base_url:
        return None
    base = base_url.rstrip("/")
    if not project:
        return None
    encoded = quote(str(project), safe="")
    if commit_sha:
        if not _COMMIT_SHA.match(commit_sha):
            return None
        suffix = f"/-/commit/{commit_sha}"
        if path:
            suffix = f"/-/blob/{commit_sha}/{quote(path, safe='/')}"
        return f"{base}/{encoded}{suffix}"
    return f"{base}/{encoded}"


def build_aws_console_url(arn: str | None, region: str | None) -> str | None:
    if not arn or not arn.startswith("arn:aws:lambda:") or not region:
        return None
    if region not in arn.split(":")[3]:
        return None
    encoded = quote(arn, safe="")
    return f"https://{region}.console.aws.amazon.com/lambda/home?region={region}#/functions/{encoded}"
