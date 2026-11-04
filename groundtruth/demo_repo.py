from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from groundtruth.utils.hashing import sha256_hex

HISTORICAL_DATE = "2026-09-08T10:15:00+00:00"
INITIAL_DATE = "2026-09-01T09:00:00+00:00"
UPDATE_DATE = "2026-10-28T14:00:00+00:00"
DOCS_DATE = "2026-11-01T08:30:00+00:00"
AUTHOR_NAME = "Priya Raman"
AUTHOR_EMAIL = "priya.raman@northgate.io"
REPOSITORY_URL = "https://gitlab.com/northgate/data-pipelines"
FILE_PATH = "environments/prod/orders/lambda.tf"
DOCS_PATH = "README.md"
FUNCTION_NAME = "orders-transformer"
RESOURCE_ADDRESS = "module.orders.aws_lambda_function.transformer"
MODULE_NAME = "orders"

HISTORICAL_FILE = f"""# Managed by Terraform — module: orders
# Terraform address: {RESOURCE_ADDRESS}

resource "aws_lambda_function" "transformer" {{
  function_name = "{FUNCTION_NAME}"
  role          = aws_iam_role.orders.arn
  runtime       = "python3.12"
  handler       = "app.handler"
  memory_size   = 512
  timeout       = 30

  tags = {{
    Environment = "prod"
    Team        = "platform-orders"
    Service     = "orders-api"
  }}
}}
"""

UPDATED_FILE = HISTORICAL_FILE.replace('runtime       = "python3.12"', 'runtime       = "python3.13"')

INITIAL_README = """# northgate/data-pipelines

Terraform/OpenTofu roots for Northgate data platform workloads (orders, analytics, payments).
Each environment directory maps to one Scalr workspace. See `environments/` for roots.
"""

UPDATED_README = (
    INITIAL_README + "\nOwnership note: orders workloads are investigated with GroundTruth before changes.\n"
)


def _git(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    merged = os.environ.copy()
    merged.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": AUTHOR_NAME,
            "GIT_AUTHOR_EMAIL": AUTHOR_EMAIL,
            "GIT_COMMITTER_NAME": AUTHOR_NAME,
            "GIT_COMMITTER_EMAIL": AUTHOR_EMAIL,
        }
    )
    if env:
        merged.update(env)
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=merged,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "git command failed")
    return completed.stdout.strip()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))


def _commit(cwd: Path, message: str, when: str) -> str:
    _git(["add", "-A"], cwd)
    _git(
        ["commit", "-m", message],
        cwd,
        env={"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when},
    )
    return _git(["rev-parse", "HEAD"], cwd)


def _fallback_manifest(repo_path: Path) -> dict[str, Any]:
    synthetic = sha256_hex(f"groundtruth-demo|{repo_path}")[:40]
    return {
        "git_available": False,
        "repo_path": str(repo_path),
        "repository_url": REPOSITORY_URL,
        "head_sha": synthetic,
        "historical_sha": synthetic,
        "file_path": FILE_PATH,
        "docs_path": DOCS_PATH,
        "function_name": FUNCTION_NAME,
        "resource_address": RESOURCE_ADDRESS,
        "author_name": AUTHOR_NAME,
        "author_email": AUTHOR_EMAIL,
        "committed_at": HISTORICAL_DATE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def ensure_demo_repo(repo_path: Path, *, force: bool = False) -> dict[str, Any]:
    manifest_path = repo_path.parent / "demo_repo_manifest.json"
    if not force and manifest_path.exists() and repo_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("head_sha") and (repo_path / ".git").exists():
                return manifest
        except (OSError, json.JSONDecodeError):
            pass
    if not shutil.which("git"):
        manifest = _fallback_manifest(repo_path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest
    if force and repo_path.exists():
        shutil.rmtree(repo_path)
    repo_path.mkdir(parents=True, exist_ok=True)
    try:
        if not (repo_path / ".git").exists():
            _git(["init", "-b", "main"], repo_path)
            _git(["config", "user.name", AUTHOR_NAME], repo_path)
            _git(["config", "user.email", AUTHOR_EMAIL], repo_path)
            _git(["config", "core.autocrlf", "false"], repo_path)
            _git(["config", "commit.gpgsign", "false"], repo_path)
            _git(["remote", "add", "origin", f"{REPOSITORY_URL}.git"], repo_path)
        _write(repo_path / DOCS_PATH, INITIAL_README)
        _commit(repo_path, "Initialize data pipelines repository", INITIAL_DATE)
        _write(repo_path / FILE_PATH, HISTORICAL_FILE)
        historical_sha = _commit(repo_path, "Add orders transformer Lambda module", HISTORICAL_DATE)
        _write(repo_path / FILE_PATH, UPDATED_FILE)
        _commit(repo_path, "Refresh orders transformer runtime", UPDATE_DATE)
        _write(repo_path / DOCS_PATH, UPDATED_README)
        head_sha = _commit(repo_path, "Document ownership investigation practice", DOCS_DATE)
        manifest = {
            "git_available": True,
            "repo_path": str(repo_path),
            "repository_url": REPOSITORY_URL,
            "head_sha": head_sha,
            "historical_sha": historical_sha,
            "file_path": FILE_PATH,
            "docs_path": DOCS_PATH,
            "function_name": FUNCTION_NAME,
            "resource_address": RESOURCE_ADDRESS,
            "author_name": AUTHOR_NAME,
            "author_email": AUTHOR_EMAIL,
            "committed_at": HISTORICAL_DATE,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest
    except Exception:
        manifest = _fallback_manifest(repo_path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest
