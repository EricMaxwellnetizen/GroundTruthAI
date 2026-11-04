from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIO = ROOT / "video" / "assets" / "audio"
AUDIO.mkdir(parents=True, exist_ok=True)

VOICE = "en-US-AndrewNeural"
RATE = "-5%"
PITCH = "-2Hz"

SCENES = {
    "01_hook": ("A Lambda is live in production. It isn't in the Terraform repo. And nobody can tell you who owns it."),
    "02_problem": (
        "Before anyone deletes it, re-imports it, or changes it, you need one answer: "
        "what evidence exists, and where does that evidence end?"
    ),
    "03_reveal": (
        "This is GroundTruth. Give it a Lambda ARN, or replay a known-answer case. "
        "It traces ownership across AWS, Scalr state and run history, Git, CloudTrail, and CloudWatch. "
        "Read-only. Deterministic. Auditable."
    ),
    "04_finding": (
        "The result: historical owner found, with high confidence. No active Scalr binding. "
        "But one historical binding matches the exact ARN. The Terraform address... the workspace... "
        "the run... the actor. That's a historical manager, not a current owner."
    ),
    "05_evidence": (
        "Every conclusion opens into evidence. The graph separates exact ARN matches from inferred relationships. "
        "The timeline shows when each fact was observed. Every record carries its source, timestamp, match type, "
        "and limitation. When a source can't be checked, you see a coverage gap, not an empty result."
    ),
    "06_ai": (
        "This is where Muse Spark comes in. It reads only sanitized evidence and explains what it means. "
        "But it cannot invent an owner, change the status, or authorize a change. Every factual claim must cite an evidence ID. "
        "If the model fails or cites something unknown, GroundTruth falls back to a deterministic explanation. "
        "The AI is advisory. The engine is authoritative."
    ),
    "07_report": (
        "The result ships as an evidence bundle: JSON and Markdown. Account IDs redacted by default. "
        "SHA-256 checksum verified. This is the artifact you attach to a change request, an incident review, or an audit."
    ),
    "08_hardstop": (
        "And the engine knows when to stop. Same Lambda. Two active Scalr workspaces claiming the exact same ARN. "
        "GroundTruth returns multiple active owners, and blocks adoption. It does not pick a winner."
    ),
    "09_underhood": (
        "Under the hood: eight read-only connectors, a deterministic match hierarchy, seven terminal statuses, "
        "checksummed exports, and forty-eight tests. No apply, import, delete, or invoke. "
        "Missing evidence is a coverage gap, not proof of absence."
    ),
    "10_close": (
        "For platform, SRE, and compliance teams, GroundTruth turns a scattered evidence hunt into a repeatable, "
        "auditable investigation. Find the owner before you touch the resource."
    ),
}


def main() -> None:
    manifest = {}
    for key, text in SCENES.items():
        media = AUDIO / f"{key}.mp3"
        subs = AUDIO / f"{key}.srt"
        print(f"Generating {key}...")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "edge_tts",
                "--voice",
                VOICE,
                f"--rate={RATE}",
                f"--pitch={PITCH}",
                "--text",
                text,
                "--write-media",
                str(media),
                "--write-subtitles",
                str(subs),
                "--no-progress",
            ],
            check=True,
            cwd=str(ROOT),
        )
        manifest[key] = {"text": text, "media": str(media), "subs": str(subs)}
    (AUDIO / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Done.")


if __name__ == "__main__":
    main()
