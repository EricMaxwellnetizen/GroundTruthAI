from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.config import Settings
from groundtruth.services.freshness import CONTRACTS, EndpointContract

Fetcher = Callable[[str], str]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def default_fetcher(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "GroundTruth-Freshness/1.3"})
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - allowlisted doc hosts only
        return response.read(400_000).decode("utf-8", errors="ignore")


class EndpointWatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector: str
    docs_url: str
    baseline_hash: str | None = None
    current_hash: str | None = None
    changed: bool = False
    reachable: bool = True
    action: str = ""


class FreshnessRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: datetime
    watches: list[EndpointWatch] = Field(default_factory=list)
    updates_applied: list[str] = Field(default_factory=list)
    patch_proposal: str = ""
    ai_used: bool = False


class FreshnessAgent:
    """Watches official API docs, detects drift, and auto-applies safe updates.

    Automatic tier (always on when the agent runs):
      - re-baselines doc hashes and bumps the contract registry's checked_on
        in the local override file that the deterministic connectors' freshness
        state is derived from;
      - writes a patch proposal + review brief for anything structural.
    Code files themselves are never rewritten unattended: structural changes
    are proposed with the exact files to touch, ready for a one-click reviewed
    commit. That boundary is what keeps the deterministic engine trustworthy.
    """

    def __init__(self, store_dir: Path, settings: Settings | None = None, fetcher: Fetcher | None = None) -> None:
        self.dir = Path(store_dir)
        self.settings = settings or Settings.from_env()
        self.fetcher = fetcher or default_fetcher
        self.baseline_path = self.dir / "freshness_baseline.json"
        self.override_path = self.dir / "contracts_override.json"
        self.proposal_path = self.dir / "PATCH_PROPOSAL.md"

    def _baseline(self) -> dict[str, str]:
        if not self.baseline_path.exists():
            return {}
        try:
            return json.loads(self.baseline_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return {}

    def run(self, contracts: list[EndpointContract] | None = None, *, auto_apply: bool = True) -> FreshnessRun:
        contracts = contracts or CONTRACTS
        baseline = self._baseline()
        watches: list[EndpointWatch] = []
        changed_contracts: list[EndpointContract] = []
        for contract in contracts:
            base = baseline.get(contract.docs_url)
            try:
                content = self.fetcher(contract.docs_url)
                current = _hash(content)
                reachable = True
            except Exception:
                current, reachable = None, False
            changed = bool(reachable and base and current and base != current)
            if changed:
                changed_contracts.append(contract)
            watches.append(
                EndpointWatch(
                    connector=contract.connector,
                    docs_url=contract.docs_url,
                    baseline_hash=base,
                    current_hash=current,
                    changed=changed,
                    reachable=reachable,
                    action="drift detected — proposal drafted"
                    if changed
                    else ("baseline recorded" if reachable else "docs unreachable — kept last baseline"),
                )
            )
        updates: list[str] = []
        proposal = ""
        ai_used = False
        if auto_apply:
            self.dir.mkdir(parents=True, exist_ok=True)
            new_baseline = {w.docs_url: w.current_hash for w in watches if w.current_hash}
            merged = {**baseline, **new_baseline}
            self.baseline_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
            if new_baseline:
                updates.append(f"Re-baselined {len(new_baseline)} doc hash(es).")
            if changed_contracts:
                overrides = {
                    c.connector: {"checked_on": _utcnow().date().isoformat(), "operation": c.operation}
                    for c in changed_contracts
                }
                self.override_path.write_text(json.dumps(overrides, indent=2), encoding="utf-8")
                updates.append(
                    f"Auto-updated contract registry for: {', '.join(overrides)} (checked_on bumped; deterministic surface unchanged)."
                )
                proposal, ai_used = self._proposal(changed_contracts, watches)
                self.proposal_path.write_text(proposal, encoding="utf-8")
                updates.append("Patch proposal written to .groundtruth/PATCH_PROPOSAL.md for reviewed code changes.")
        return FreshnessRun(
            at=_utcnow(), watches=watches, updates_applied=updates, patch_proposal=proposal, ai_used=ai_used
        )

    def _proposal(self, changed: list[EndpointContract], watches: list[EndpointWatch]) -> tuple[str, bool]:
        lines = ["# Freshness patch proposal (auto-generated)", "", f"Generated: {_utcnow().isoformat()}", ""]
        for contract in changed:
            lines += [
                f"## {contract.connector} — {contract.operation}",
                f"- Docs: {contract.docs_url}",
                f"- Deterministic surface: `{contract.deterministic_surface}`",
                "- Action: re-verify parameters/response shape against the new docs, update the connector + its tests, then bump checked_on in a reviewed commit.",
                "",
            ]
        brief = "\n".join(lines)
        if self.settings.ai_configured:
            try:
                from openai import OpenAI

                client = OpenAI(
                    api_key=self.settings.active_api_key, base_url=self.settings.active_base_url, timeout=60
                )
                response = client.chat.completions.create(
                    model=self.settings.active_model,
                    temperature=0.1,
                    max_tokens=800,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a connector-maintenance analyst. Given doc-drift items, list the exact verification steps and likely parameter changes. Never invent endpoints.",
                        },
                        {"role": "user", "content": brief},
                    ],
                )
                analysis = (response.choices[0].message.content or "").strip()
                if analysis:
                    return brief + "\n## AI analysis\n\n" + analysis + "\n", True
            except Exception:
                pass
        return brief, False
