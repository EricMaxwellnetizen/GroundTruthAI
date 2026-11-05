from __future__ import annotations

import re
from pathlib import Path

ALLOWED_KEYS = {
    "GROUNDTRUTH_MODE",
    "AWS_PROFILE",
    "AWS_REGION",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "SCALR_BASE_URL",
    "SCALR_API_TOKEN",
    "SCALR_TF_RESOURCE_USAGE_FILTER",
    "GIT_REPO_PATH",
    "GITLAB_BASE_URL",
    "GITLAB_PROJECT_ID",
    "GITLAB_TOKEN",
    "MODEL_API_KEY",
    "META_API_BASE_URL",
    "META_MODEL",
    "AI_ENABLED",
    "GROUNDTRUTH_AI_PROVIDER",
    "LLAMA_API_BASE_URL",
    "LLAMA_MODEL",
    "LLAMA_API_KEY",
    "GROUNDTRUTH_AUTOMATION_ENABLED",
    "GROUNDTRUTH_ALLOW_LIVE_ACTIONS",
    "GROUNDTRUTH_FRESHNESS_AUTO",
    "GROUNDTRUTH_FRESHNESS_INTERVAL_DAYS",
}

SECRET_KEYS = {
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "SCALR_API_TOKEN",
    "GITLAB_TOKEN",
    "MODEL_API_KEY",
    "LLAMA_API_KEY",
}

_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _KEY_RE.match(stripped)
        if match:
            values[match.group(1)] = stripped[match.end() :].strip().strip('"').strip("'")
    return values


def _render(existing_text: str, updates: dict[str, str]) -> str:
    lines = existing_text.splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        match = _KEY_RE.match(line.strip())
        key = match.group(1) if match else None
        if key and key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    return "\n".join(out).rstrip() + "\n"


def mask_value(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return "••••" + value[-4:]


class CredentialVault:
    """Writes UI-entered credentials to .env and a gitignored backup copy.

    Secrets are write-only from the UI's perspective: status reporting returns
    masked values, never the secret itself. Both files live outside git
    (.env and .groundtruth/ are gitignored).
    """

    def __init__(self, project_root: Path) -> None:
        self.root = Path(project_root)
        self.env_path = self.root / ".env"
        self.backup_path = self.root / ".groundtruth" / "credentials.backup.env"

    def save(self, updates: dict[str, str]) -> dict[str, str]:
        clean = {k: str(v).strip() for k, v in updates.items() if k in ALLOWED_KEYS}
        existing = self.env_path.read_text(encoding="utf-8") if self.env_path.exists() else ""
        rendered = _render(existing, clean)
        self.env_path.write_text(rendered, encoding="utf-8")
        self.backup_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_path.write_text(rendered, encoding="utf-8")
        return self.status()

    def status(self) -> dict[str, str]:
        text = ""
        if self.backup_path.exists():
            text = self.backup_path.read_text(encoding="utf-8")
        elif self.env_path.exists():
            text = self.env_path.read_text(encoding="utf-8")
        values = _parse_env(text)
        return {
            key: (mask_value(value) if key in SECRET_KEYS else value)
            for key, value in values.items()
            if key in ALLOWED_KEYS and value
        }

    def configured_keys(self) -> set[str]:
        text = ""
        if self.env_path.exists():
            text = self.env_path.read_text(encoding="utf-8")
        return {k for k, v in _parse_env(text).items() if k in ALLOWED_KEYS and v}
