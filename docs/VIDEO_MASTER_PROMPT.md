# GroundTruth — Meta Hackathon 2026 Video Master Prompt

> **Read this first.** Do not paste the master prompt into a pure text-to-video model and expect a working product demo. The product UI must be recorded from the running Streamlit app. Use AI for the voice, music, motion graphics, captions, and edit assist. Generated UI will look fake, will not match the real app, and will lose the 25% Demo score.

## The winning angle

Most hackathon videos show a chatbot and a dashboard. This one should show something rarer: **a working system that knows when not to trust the AI.**

The story is not "AI finds the owner." The story is:

> **GroundTruth finds the evidence. Deterministic code decides. Muse Spark explains. The engineer acts with receipts.**

That is the line the judges should remember.

---

## Copy-paste master prompt

```text
ROLE

You are a senior product demo director, hackathon judge, and video editor. You have directed technical launch films for developer tools. You know that judges reward clarity, proof, and craft — not hype. You are producing the official 3-minute submission video for GroundTruth for the Meta Global AI Developer Hackathon 2026.

Your job is not to make a pretty AI video. Your job is to make a judge believe, in under three minutes, that GroundTruth is a real working product with a novel trust model and a clear real-world impact.

MISSION

Make a judge understand, within 10 seconds, that this is a real production problem.
Make them understand, within 60 seconds, that this is a real working product.
Make them remember, at the end, one line: "The AI explains. The engine decides."

The video must be all-encompassing but never a feature tour. Every shot must either create tension, prove the product works, or prove the trust model.

THE ONE NON-NEGOTIABLE RULE

Use real screen recordings of the running app. Do not generate, mock up, animate, or "recreate" the product UI. If a screen is missing, request a capture; do not invent it. AI may generate only abstract b-roll, voice, music, and motion graphics. Every button click, status pill, evidence count, checksum, and download in the video must come from the actual app.

THE SOURCE OF TRUTH — DO NOT INVENT FEATURES

Product: GroundTruth.
Tagline: "Find the owner before you touch the resource."
Category: local-first, read-only AWS resource lineage investigator.
Core question: "What evidence exists for this resource's ownership, and where exactly does that evidence end?"

What it does:
- Accepts a Lambda ARN or function name, or replays a known-answer fixture case.
- Correlates AWS Lambda identity, IAM role metadata, Scalr resource usage and workspace/run/state history, local Git or optional GitLab, CloudTrail management events, CloudWatch metrics, and optional CloudWatch Omni context.
- Runs a deterministic lineage engine with exact-identity match tiers and seven terminal statuses.
- Produces an evidence graph, timeline, dependency view, coverage gaps, recommendations, and an advisory AI explanation.
- Exports a checksummed JSON bundle and Markdown report with account IDs redacted by default.
- Stores investigation metadata in SQLite.
- Exposes a default-deny read-only MCP adapter.
- Has 127 tests, Ruff-clean code, a Docker image, and a non-root container runtime.
- Is read-only by design: no apply, import, delete, invoke, mutate, or write-back controls.

Statuses:
CURRENT_OWNER_FOUND, HISTORICAL_OWNER_FOUND, MULTIPLE_ACTIVE_OWNERS, CANDIDATE_LINEAGE, UNATTRIBUTED_IN_CHECKED_SOURCES, INSUFFICIENT_ACCESS, IDENTITY_AMBIGUOUS.

Confidence labels:
HIGH, MEDIUM, LOW, UNKNOWN.

Meta AI:
- Meta Muse Spark 1.3 through the Meta Model API.
- The model receives a sanitized evidence bundle.
- It returns structured JSON through a submit_explanation tool call.
- Every factual statement must cite a known evidence ID.
- Validation rejects unknown citations or any attempt to change the deterministic status, confidence, ownership records, coverage, or recommendation.
- If the model is unavailable or invalid, the app falls back to a deterministic explanation generated from the same evidence.
- The AI is advisory. The engine is authoritative.

Demo mode:
- The recording uses synthetic fixture data.
- The UI badge says "DEMO / FIXTURE DATA."
- The fixture data is synthetic. No live AWS, Scalr, GitLab, or CloudTrail scan is happening.
- Never imply a live production scan occurred. If you mention the live connectors, say they are implemented and read-only; do not claim they were exercised unless the recording actually shows it.
- The fixture mode is a feature: the investigation is reproducible and offline.

Exact values from case A (use the values visible in the recording; if they differ, use the recording and update the voiceover):
- Resource: orders-transformer.
- ARN: arn:aws:lambda:ap-south-1:123456789012:function:orders-transformer.
- Region: ap-south-1.
- Status: HISTORICAL_OWNER_FOUND.
- Confidence: HIGH.
- Evidence: 12.
- Coverage gaps: 1.
- Current owners: 0.
- Historical Scalr bindings matching the exact ARN: 1.
- Historical workspace: orders-prod.
- Terraform address: module.orders.aws_lambda_function.transformer.
- Historical run: run-historical-042.
- Run actor: arjun.mehta@example.com.
- Run status: applied.
- Run timestamp: 2026-09-08.
- The UI says: "No active state binding was found, but 1 historical Scalr binding(s) match the exact ARN."

Exact values from case B:
- Status: MULTIPLE_ACTIVE_OWNERS.
- Confidence: HIGH.
- Evidence: 15.
- Two active Scalr workspaces claim the exact same Lambda ARN: orders-prod and orders-prod-v2.
- Adoption is unsafe and blocked.
- The app does not silently choose a winner.

Five known-answer fixture cases:
A — Historical owner found — HISTORICAL_OWNER_FOUND / HIGH.
B — Multiple active owners — MULTIPLE_ACTIVE_OWNERS / HIGH.
C — Candidate lineage only — CANDIDATE_LINEAGE / LOW.
D — Insufficient access — INSUFFICIENT_ACCESS / UNKNOWN.
E — Current owner found — CURRENT_OWNER_FOUND / HIGH.

Do not claim:
- "Live AWS scan" or "we scanned production" while in fixture mode.
- "The AI finds the owner" or "the AI decides."
- "Real-time monitoring."
- "Supports every cloud." It is AWS Lambda first.
- "Autonomous remediation" or "agentic write-back." It is read-only.
- "Production-ready multi-tenant SaaS." It is a local-first MVP.
- "Blockchain," "zero-knowledge," or any technology not in the source of truth.

Words to avoid:
revolutionary, game-changing, seamless, magic, unleash, supercharge, cutting-edge, next-generation, paradigm shift.

AUDIENCE AND RUBRIC

The judges are technical. They are scoring four things:

Impact — 30%
- The real-world pain: a production Lambda with no clear Terraform/state owner; evidence split across AWS, Scalr, Git, CloudTrail, and CloudWatch; the risk of deleting or re-importing the wrong resource.
- Who benefits: platform engineering, SRE, DevOps, cloud infrastructure, compliance, and FinOps teams.
- Why it matters: safer changes, faster investigations, auditable evidence for change requests and incident reviews.

Use of Meta AI tooling — 25%
- Muse Spark is not a thin chat wrapper. It is a constrained explanation layer over a deterministic evidence engine.
- Show the structured tool call, the evidence-ID citations, the validation boundary, and the deterministic fallback.
- The memorable idea: "AI explains. Engine decides." This is verifiable AI for production infrastructure.

Technical depth and execution — 20%
- Eight read-only source adapters, a deterministic match hierarchy, seven terminal statuses, coverage gaps, checksummed exports, redaction, SQLite metadata, MCP default-deny, 127 tests, Docker, and a non-root runtime.
- Show proof, don't just list it. Use real UI, real terminal output, and real artifacts.

Demo — 25%
- Working product, real clicks, real result, real export.
- Clear input → processing → output → second case → audit artifact.
- No dead air, no long loading screens, no fake UI, no slide deck.
- The video itself should be well-paced, readable, and confidently narrated.

CREATIVE DIRECTION

Tone:
Calm, precise, cinematic-technical. Quiet confidence. A senior engineer explaining a serious finding — not a startup pitch, not a movie trailer, not a hype reel.

Visual language:
- Match the GroundTruth UI: ink black, warm cream, teal, muted amber, and one red accent for the hard stop.
- Editorial serif headlines; clean sans-serif body; monospace for ARNs, evidence IDs, checksums, and terminal output.
- Thin rules, generous negative space, small uppercase labels, subtle grain.
- The product UI should look like the hero. Do not cover it with giant text, glowing boxes, or meme captions.
- Use the real dark sidebar and light content area. Do not invert the UI or apply a heavy color grade.
- Use a custom cursor with a soft click ring. Move it deliberately. Never let it jitter or hunt for a button.
- Use smooth 1.15x–1.6x push-ins for detail shots. Hold long enough to read.
- Cut on action. Average shot length 2.5–3.5 seconds. No slow fades except at the end.
- Use hard cuts and match cuts. One 6-frame dissolve at the chapter change into the AI section is allowed. No zoom transitions, no spin transitions, no whooshes on every cut.

Typography:
- Headlines: a high-contrast editorial serif (for example, Fraunces, DM Serif Display, or the app's existing display face).
- Body and captions: Inter or the app's sans-serif.
- Technical labels: JetBrains Mono or the app's monospace.
- On-screen text: maximum 8 words per card. Never cover the UI label it is describing.
- Keep a persistent small "DEMO / FIXTURE DATA" label in the lower third whenever the full sidebar badge is cropped out.

Pacing:
- First product frame by 0:16.
- First real result by 0:44.
- First "trust" moment by 1:22.
- Hard stop by 2:00.
- End card by 2:45.
- Total runtime: 2:48–2:55. Never exceed 3:00.

STORY ARC — SHOT-BY-SHOT

Use this as the edit blueprint. Times are targets; protect the beats, not the seconds.

0:00–0:10 — COLD OPEN: THE ORPHAN
Picture:
- Black screen. Three short text cards appear one at a time, centered, small, white on black.
- Card 1: "A Lambda is live in production."
- Card 2: "It is not in the Terraform repo."
- Card 3: "Nobody knows who owns it."
- Optional: a very subtle low pulse under the text. No glitch effects, no matrix rain, no robot imagery.
Voiceover:
"A Lambda is live in production. It isn't in the Terraform repo. And nobody can tell you who owns it."
On-screen text:
"A PRODUCTION LAMBDA" / "NOT IN TERRAFORM" / "OWNER UNKNOWN"
Sound:
Low sub pulse begins. No music melody yet.

0:10–0:18 — THE QUESTION
Picture:
- Cut to a 3-second motion graphic: five labeled nodes (AWS, Scalr, Git, CloudTrail, CloudWatch) connected by thin lines to a single Lambda node. The lines flicker and one gap remains unconnected.
- Cut to the real Home screen. Slow push-in on the tagline "Find the owner before you touch the resource." Hold for 2 seconds.
Voiceover:
"Before anyone deletes it, re-imports it, or changes it, you need one answer: what evidence exists — and where does that evidence end?"
On-screen text:
"EVIDENCE, WITH RECEIPTS"
Sound:
Soft whoosh into the Home screen. Music pulse continues.

0:18–0:36 — PRODUCT REVEAL: RUN THE CASE
Picture:
- Real Home screen. The "DEMO / FIXTURE DATA" badge is visible.
- Show the five known-answer cases. Scroll just enough to show that every terminal status is covered.
- Move the cursor to Case A, "A - Historical owner found." Click "Run this case."
- Hold on the real progress panel. Show the stage names: Fixture sources, AWS Lambda, Scalr resource usage, Git / repository, CloudTrail events, CloudWatch metrics, CloudWatch Omni, Deterministic correlation, Muse Spark explanation, Export.
- Speed-ramp the waiting time 3x–4x. Keep the stage labels readable. Do not show dead air.
Voiceover:
"This is GroundTruth. Give it a Lambda ARN, or replay a known-answer case. It traces ownership across AWS, Scalr state and run history, Git, CloudTrail, and CloudWatch. Read-only. Deterministic. Auditable."
On-screen text:
"READ-ONLY · DETERMINISTIC · AUDITABLE"
"5 KNOWN-ANSWER CASES · EVERY TERMINAL STATUS"
Sound:
Soft UI clicks. A subtle tick as each stage completes. Music begins to build at 0:30.

0:36–1:02 — THE FINDING: HISTORICAL, NOT CURRENT
Picture:
- Cut to Lineage overview. Hold on the status pill, confidence, and evidence count.
- Highlight: HISTORICAL_OWNER_FOUND, HIGH, 12 evidence.
- Scroll to "No active state binding was found, but 1 historical Scalr binding(s) match the exact ARN."
- Continue to the Historical managers card. Highlight the exact ARN, workspace orders-prod, Terraform address module.orders.aws_lambda_function.transformer, run run-historical-042, actor arjun.mehta@example.com, and the 2026-09-08 timestamp.
- Use a 1.3x push-in on the Terraform address, then a 1.3x push-in on the run actor. Do not show both at once in a way that is unreadable.
Voiceover:
"The result: HISTORICAL_OWNER_FOUND, with high confidence. No active Scalr binding. But one historical binding matches the exact ARN. The Terraform address... the workspace... the run... the actor. That's a historical manager — not a current owner."
On-screen text:
"HISTORICAL_OWNER_FOUND · HIGH"
"EXACT ARN MATCH"
"HISTORICAL ≠ CURRENT"
Sound:
Music opens slightly. A single soft confirmation tone on "exact ARN."

1:02–1:22 — THE EVIDENCE CHAIN
Picture:
- Evidence graph. Show the Lambda node, Scalr workspace, run, Git commit, CloudTrail event, and CloudWatch metric.
- Click or hover one exact edge. Hold on the provenance panel: evidence ID, source, observed timestamp, match type, limitation.
- Cut to Timeline. Scroll through the dated events. Show that exact matches and inferred links are visually distinct.
- Cut to the coverage-gap area. Highlight the gap with a soft amber pulse, never red.
Voiceover:
"Every conclusion opens into evidence. The graph separates exact ARN matches from inferred relationships. The timeline shows when each fact was observed. Every record carries its source, timestamp, match type, and limitation. When a source can't be checked, you see a coverage gap — not an empty result."
On-screen text:
"EVERY CLAIM → EVIDENCE ID"
"EXACT vs INFERRED"
"GAP, NOT GUESS"
Sound:
Soft clicks on each evidence selection. No whooshes.

1:22–1:44 — META AI: THE SEATBELT
Picture:
- Cut to AI explanation. Hold on the header: "Muse Spark explains; the deterministic engine decides."
- Show the "Muse Spark" pill and the model name muse-spark-1.3. Show the "Tool calls: 1" metric.
- Scroll through the summary and the established facts. Each fact has evidence chips. Hover one chip; show the evidence ID.
- Briefly show the advisory caption: "The AI explanation is advisory. The deterministic status, confidence, and recommendation on the Lineage and Evidence report pages are authoritative."
- Optional split screen: left side "MUSE SPARK EXPLAINS"; right side the Lineage status with a small lock icon and "ENGINE DECIDES."
Voiceover:
"This is where Muse Spark comes in. It reads only sanitized evidence and explains what it means. But it cannot invent an owner, change the status, or authorize a change. Every factual claim must cite an evidence ID. If the model fails or cites something unknown, GroundTruth falls back to a deterministic explanation. The AI is advisory. The engine is authoritative."
On-screen text:
"MUSE SPARK 1.3 · META MODEL API"
"AI EXPLAINS · ENGINE DECIDES"
"STRUCTURED TOOL CALL · CITATION VALIDATION · FALLBACK"
Sound:
Music drops to a single low pulse under this section. The voice is the focus. A soft click when the evidence chip opens.

NOTE: Only show the "Muse Spark" pill if the recording actually used Muse Spark. If the model is unavailable and the app shows "Deterministic fallback," do not fake it. Either re-record after a successful Muse Spark call, or keep the fallback and say honestly: "This offline run used the deterministic fallback; the Muse Spark integration is the same path." A fake AI shot is worse than an honest fallback.

1:44–2:00 — THE RECEIPTS
Picture:
- Cut to Evidence report. Hold on 12 evidence records, 1 coverage gap, Redaction Applied, Checksum Verified.
- Show the SHA-256 checksum line. Do not read the whole hash.
- Click "Download JSON bundle." Show the download toast.
- Click "Download Markdown report." Show the download toast.
- Optional: 2-second cut of the downloaded Markdown open in a clean editor, showing the status, evidence table, limitations, and checksum. Blur any local file path.
Voiceover:
"The result ships as an evidence bundle: JSON and Markdown. Account IDs redacted by default. SHA-256 checksum verified. This is the artifact you attach to a change request, an incident review, or an audit."
On-screen text:
"12 EVIDENCE · 1 COVERAGE GAP"
"REDACTED BY DEFAULT"
"SHA-256 VERIFIED"
Sound:
Soft chime on "checksum verified." Music returns.

2:00–2:12 — THE HARD STOP
Picture:
- Quick cut to Home. Click Case B, "B - Multiple active owners." Run it. Speed-ramp the progress.
- Cut to Lineage overview. Hold on MULTIPLE_ACTIVE_OWNERS, HIGH, 15 evidence.
- Show the two active workspaces: orders-prod and orders-prod-v2. Both claim the exact same ARN.
- Show "adoption is unsafe" / blocked. Add a restrained red lock or red rule line in post. Do not turn the screen red.
Voiceover:
"And the engine knows when to stop. Same Lambda. Two active Scalr workspaces claiming the exact same ARN. GroundTruth returns MULTIPLE_ACTIVE_OWNERS and blocks adoption. It does not pick a winner."
On-screen text:
"MULTIPLE_ACTIVE_OWNERS · HIGH"
"2 ACTIVE OWNERS · ADOPTION BLOCKED"
"NO SILENT WINNER"
Sound:
A single low boom on "blocks adoption." Then silence for 0.4 seconds. This is the tension beat.

2:12–2:28 — UNDER THE HOOD
Picture:
- Cut to a clean motion graphic of the architecture: Streamlit UI → InvestigationOrchestrator → eight read-only connectors → deterministic LineageEngine → LineageResult / EvidenceBundle → SQLite + JSON/Markdown + AIExplainService. Use the real architecture from docs/ARCHITECTURE.md. Keep it simple; no more than 10 nodes.
- Quick proof montage, 1.5–2 seconds each:
  1. Real terminal: python -m pytest -q → 127 passed. Clean font, no personal paths, no secrets.
  2. Real terminal or Docker output: health check → ok; runtime user uid=10001(groundtruth). Do not fabricate.
  3. Real Settings/connections page or policy file: read-only sources, no write actions.
- Optional 1-second grid of four real pages: Resource inventory, Dependencies & activity, Timeline, Settings/connections. Label it "10-page workspace."
Voiceover:
"Under the hood: eight read-only connectors, a deterministic match hierarchy, seven terminal statuses, checksummed exports, and forty-eight tests. No apply, import, delete, or invoke. Missing evidence is a coverage gap — not proof of absence."
On-screen text:
"8 READ-ONLY CONNECTORS · 7 STATUSES · 127 TESTS"
"READ-ONLY BY DESIGN · MCP DEFAULT-DENY"
"10-PAGE WORKSPACE"
Sound:
Music pulses with the montage cuts. No typing sounds unless they are real.

2:28–2:50 — IMPACT AND CLOSE
Picture:
- Return to the Home screen or a slow three-screen montage: Home → Lineage → Report. Keep the tagline visible.
- End card: "GroundTruth" in the display serif; tagline; GitHub URL; "Built with Meta Muse Spark"; "Meta Global AI Developer Hackathon 2026."
- Small print: "Demo uses synthetic fixture data. Live connectors are read-only."
- Do not add a fake QR code, fake user counts, or fake company logos.
Voiceover:
"For platform, SRE, and compliance teams, GroundTruth turns a scattered evidence hunt into a repeatable, auditable investigation. Find the owner before you touch the resource."
On-screen text:
"GROUNDTRUTH"
"FIND THE OWNER BEFORE YOU TOUCH THE RESOURCE"
"Built with Meta Muse Spark · Meta Global AI Developer Hackathon 2026"
Sound:
Music resolves on a warm, quiet chord. No big trailer hit. Let the tagline land.

FULL VOICEOVER SCRIPT — RECORD EXACTLY

A Lambda is live in production.
[pause 0.3]
It isn't in the Terraform repo.
[pause 0.3]
And nobody can tell you who owns it.
[pause 0.4]

Before anyone deletes it, re-imports it, or changes it, you need one answer:
what evidence exists — and where does that evidence end?

This is GroundTruth.
Give it a Lambda ARN, or replay a known-answer case.
It traces ownership across AWS, Scalr state and run history, Git, CloudTrail, and CloudWatch.
Read-only. Deterministic. Auditable.

The result: HISTORICAL_OWNER_FOUND, with high confidence.
No active Scalr binding.
But one historical binding matches the exact ARN.
The Terraform address... the workspace... the run... the actor.
That's a historical manager — not a current owner.

Every conclusion opens into evidence.
The graph separates exact ARN matches from inferred relationships.
The timeline shows when each fact was observed.
Every record carries its source, timestamp, match type, and limitation.
When a source can't be checked, you see a coverage gap — not an empty result.

This is where Muse Spark comes in.
It reads only sanitized evidence and explains what it means.
But it cannot invent an owner, change the status, or authorize a change.
Every factual claim must cite an evidence ID.
If the model fails or cites something unknown, GroundTruth falls back to a deterministic explanation.
The AI is advisory. The engine is authoritative.

And the engine knows when to stop.
Same Lambda. Two active Scalr workspaces claiming the exact same ARN.
GroundTruth returns MULTIPLE_ACTIVE_OWNERS and blocks adoption.
It does not pick a winner.

The result ships as an evidence bundle: JSON and Markdown.
Account IDs redacted by default. SHA-256 checksum verified.
This is the artifact you attach to a change request, an incident review, or an audit.

Under the hood: eight read-only connectors, a deterministic match hierarchy, seven terminal statuses, checksummed exports, and forty-eight tests.
No apply, import, delete, or invoke.
Missing evidence is a coverage gap — not proof of absence.

For platform, SRE, and compliance teams, GroundTruth turns a scattered evidence hunt into a repeatable, auditable investigation.
Find the owner before you touch the resource.

VOICE DIRECTION

Voice:
Warm, grounded, technically literate. Late 30s. Neutral accent. Calm confidence. Not an announcer, not a salesperson, not a documentary narrator. Think "senior engineer explaining a serious finding to a trusted colleague."

Pace:
145–155 words per minute. Do not rush. Cut words before you speed up the read.

Pauses:
- 0.3s after "Terraform repo."
- 0.4s after "who owns it."
- 0.3s after "exact ARN."
- 0.3s after "the actor."
- 0.4s after "not a current owner."
- 0.4s after "It does not pick a winner."
- 0.3s before the final tagline.

Pronunciation:
- GroundTruth = GROUND-truth
- Scalr = SKAY-ler
- Muse = MYOOZ
- ARN = A-R-N
- ap-south-1 = A-P south one
- IaC = eye-ay-see
- SHA-256 = S-H-A two-fifty-six
- Terraform = TERRA-form
- CloudTrail = CLOUD-trail
- CloudWatch = CLOUD-watch
- Omni = OM-nee
- GitLab = GIT-lab
- HISTORICAL_OWNER_FOUND = his-TOR-i-cal owner found
- MULTIPLE_ACTIVE_OWNERS = multiple active owners

AI voice prompt:
"Read this script as a calm, technically literate senior engineer. Warm, precise, unhurried. No hype, no smiley upsell, no movie-trailer gravity. Pause where marked. Emphasize the contrast between 'historical' and 'current,' and between 'AI explains' and 'engine decides.' Keep the final tagline quiet and confident."

SCREEN CAPTURE MANIFEST

Record at 1920x1080, 60fps if possible, 16:9. Use a clean browser profile. Hide bookmarks, extensions, notifications, and personal data. Hide the Streamlit "Deploy" menu and developer toolbar in post or via configuration. Use a large, high-contrast cursor with a soft click ring.

Capture these clips:
1. capture_01_home.mp4 — Home. Hold on the tagline. Scroll to show all five cases. Do not click yet.
2. capture_02_run_a.mp4 — Click "Run this case" on Case A. Hold the full progress panel until it completes. Do not cut.
3. capture_03_lineage_a.mp4 — Lineage overview. Scroll slowly from status to the historical managers card. Hover the exact ARN, address, run actor, and timestamp.
4. capture_04_graph.mp4 — Evidence graph. Click an exact edge. Hold on the provenance panel. Then a slow pan.
5. capture_05_timeline.mp4 — Timeline. Scroll through the events.
6. capture_06_ai.mp4 — AI explanation. Hold on the Muse Spark pill, model name, and tool-call metric. Scroll through the summary, facts, evidence chips, and advisory caption. If Muse Spark is not actually used, capture the fallback and label it honestly.
7. capture_07_report.mp4 — Evidence report. Hold on 12 evidence, 1 gap, redaction, and checksum. Click both download buttons. Capture the toasts.
8. capture_08_case_b.mp4 — Home → Case B → progress → Lineage overview. Hold on MULTIPLE_ACTIVE_OWNERS and both active workspaces.
9. capture_09_settings.mp4 — Settings/connections. 2 seconds. Show source status honestly.
10. capture_10_tests.mp4 — Terminal: python -m pytest -q → 127 passed. Clean font, no personal paths, no secrets. If the count changed, use the current number.
11. capture_11_docker.mp4 — Optional: Docker health check and non-root user. Only if it is real output.
12. capture_12_markdown.mp4 — Optional: the downloaded Markdown report open in a clean editor. Blur local paths. Hold on status, evidence table, limitations, checksum.

If a clip is missing, use the existing screenshots in docs/images/ for a still with a slow push-in. Do not generate fake UI.

MOTION GRAPHICS

Use the app's palette:
- Ink: #111111
- Cream: #F7F1E6
- Teal: #0F766E
- Muted amber: #C98A2E
- Alert red: #B42318 (only for the hard stop)
- Evidence gray: #6B7280

Graphic 1 — The orphan:
Three text cards on black. Small, centered, generous negative space. No icons, no glitch. The words do the work.

Graphic 2 — Five sources, one gap:
Five labeled nodes connected to a Lambda node. One line is missing; a small "coverage gap" label sits where the line should be. Draw it in the app's palette, not neon.

Graphic 3 — Match hierarchy:
A vertical stack: exact_arn → exact_provider_id / exact_address → workspace_relation → exact_commit_sha / exact_event_resource → exact_name_context → candidate_name → inferred_dependency. Highlight exact_arn. Keep it on screen for 3 seconds maximum.

Graphic 4 — Architecture:
Streamlit UI → InvestigationOrchestrator → 8 read-only connectors → deterministic LineageEngine → LineageResult / EvidenceBundle → SQLite + JSON/Markdown + AIExplainService. Show the AI as an advisory branch, not the center of the system. This is the visual thesis: the engine is the trunk; the model is a branch.

Graphic 5 — The trust boundary:
A simple split: left "MUSE SPARK / EXPLAINS / cites evidence IDs," right "DETERMINISTIC ENGINE / DECIDES / status, confidence, ownership." A thin vertical line between them. No scales, no gavels, no robot brains.

SOUND DESIGN

Music:
Minimal cinematic underscore. 90 BPM. Low strings, analog sub pulse, a faint clock tick. No drums until 0:30. Build at 0:36. Drop to a single pulse at 1:22 for the AI section. Return at 1:44. One low boom at 2:00. Resolve warmly at 2:28. No vocals, no EDM, no trailer hits, no stock "innovation" music.

SFX:
- Soft UI click on every real click.
- Low whoosh on major scene changes only (maximum 4 in the film).
- A single low boom on "blocks adoption."
- A soft chime on "checksum verified."
- A quiet room tone under the voice.
- No typing sounds unless they are from the real recording.

Mix:
- Voice: -16 LUFS integrated, clear, de-essed, 100ms room tone.
- Music: -24 to -20 LUFS under voice.
- Master: -14 LUFS integrated for web, true peak -1.5 dBTP.
- Duck music 4–6 dB under voice.
- Check on laptop speakers and phone speakers. Every word must be intelligible.

EDIT SPECS

- Master: 1920x1080, 16:9, 30fps or 60fps, H.264 MP4, 8–12 Mbps, AAC 320 kbps.
- Runtime: 2:48–2:55. Never over 3:00.
- Captions: burned-in optional, but always provide an SRT. Two lines max, 42 characters per line, sync within 100ms.
- Color: neutral, match the app. Do not crush blacks or add a teal-orange grade.
- Text: safe margins 5% all sides. No text over critical UI labels.
- Cursor: visible, smooth, never jittery. Hide it when it is not needed.
- Loading: speed-ramp, never show more than 1.5 seconds of an unchanging spinner.
- Transitions: hard cuts and match cuts. One 6-frame dissolve into the AI section. No zoom transitions.
- End card: 4–5 seconds. Product name, tagline, GitHub, Meta AI line, hackathon line, small fixture disclaimer.

DELIVERABLES

A. Judged master:
- 2:48–2:55, 16:9, 1080p, MP4.
- Clean audio, captions, thumbnail.

B. Vertical social cut (recommended for the Most Viral bonus):
- 9:16, 1080x1920, 40–50 seconds.
- Burned-in captions.
- Hook in the first 2 seconds.
- End card with GitHub and "Built with Meta Muse Spark."
- Use the same real footage; do not generate a separate fake UI.

C. Thumbnail:
- 1280x720.
- The Home screen or Lineage screen with the tagline.
- Maximum 6 words of overlay.
- Readable at 320px wide.

D. SRT and transcript:
- English.
- Technical terms spelled correctly.

E. Source project:
- Keep the edit project, captures, voice stems, music license, and graphics in one folder.

QA GATE — DO NOT EXPORT UNTIL EVERY ANSWER IS YES

- Does the first 10 seconds make the problem clear without jargon?
- Does the product appear by 0:16?
- Is there a real click, a real result, and a real download?
- Is the "DEMO / FIXTURE DATA" badge visible, or is there a persistent lower-third label?
- Does the video show Muse Spark actually running, with the pill and model name, not just a claim?
- Does the video show the AI's evidence-ID citations and the advisory caption?
- Does the video show the MULTIPLE_ACTIVE_OWNERS hard stop?
- Does the video show the checksum and redaction?
- Does the video explain why the AI cannot change the status?
- Are all numbers accurate? (12 evidence, 1 gap, 15 evidence, 127 tests, 7 statuses, 8 connectors.)
- Is there any fake UI, fake terminal, fake customer logo, or overclaim? If yes, cut it.
- Is the runtime under 3:00?
- Is the voice intelligible on phone speakers?
- Would a judge who knows nothing about AWS understand the value?
- Would a judge who knows AWS believe the technical claims?
- Does the last line land cleanly with no "um," "so," or trailing music?

WHAT TO CUT IF YOU ARE OVER TIME

Cut in this order:
1. The five-case scroll — keep 2 seconds.
2. The timeline shot — keep the evidence graph.
3. The Settings/breadth grid.
4. The Docker shot.
5. Shorten the architecture voiceover.

Never cut:
- The historical-vs-current distinction.
- The Muse Spark citation/guardrail shot.
- The hard stop.
- The checksum/redaction shot.
- The tagline.

JUDGE SCORECARD SELF-CHECK

Impact — 30%:
The first 10 seconds and the last 20 seconds. Does the judge feel the risk and see who benefits? Timestamps: 0:00–0:18, 2:28–2:50.

Meta AI tooling — 25%:
The AI section. Is it clear that Muse Spark is constrained, citation-validated, and fallback-safe? Timestamps: 1:22–1:44.

Technical depth — 20%:
The evidence graph, match hierarchy, checksum, architecture, tests, and read-only design. Timestamps: 1:02–1:22, 1:44–2:00, 2:12–2:28.

Demo — 25%:
Real clicks, real output, real export, real second case. Timestamps: 0:18–2:12.

OPTIONAL GENERATIVE B-ROLL PROMPTS

Use these only for abstract textures. Never for the product UI, never for text, never for fake dashboards. If the tool cannot produce clean abstract footage, skip them. The real product is enough.

1. Opening texture:
"Extreme macro of dark server-room fiber optics, teal and warm amber light, shallow depth of field, slow dolly, photorealistic, no text, no logos, no people, 4 seconds, 16:9, subtle film grain."

2. Transition texture:
"Abstract cream-colored topographic lines flowing over a dark ink background, five faint glowing nodes connected by thin teal lines, slow parallax, minimalist editorial motion design, no text, no logos, 3 seconds, 16:9."

3. Closing texture:
"A single teal line travels through a dark void, passes five faint nodes, and resolves into a calm cream field, minimal, elegant, no text, no logos, 4 seconds, 16:9."

NEGATIVE PROMPT FOR ANY GENERATIVE TOOL

No fake dashboards. No generated UI text. No floating holograms. No robot mascots. No neon cyberpunk. No stock-photo handshakes. No growth charts. No "AI magic" particles. No illegible text. No logos. No watermarks. No rapid zoom transitions. No EDM. No fake customer quotes. No fake metrics.

END PROMPT
```

---

## Short version for tools with prompt limits

If the AI tool cannot accept the full prompt, use this:

```text
Create a 2:50 hackathon demo video for GroundTruth, a read-only AWS resource lineage investigator. Use only real screen recordings of the running Streamlit app; never generate fake UI. Open with a production Lambda that is not in Terraform and has no known owner. Show Case A: HISTORICAL_OWNER_FOUND, HIGH confidence, exact ARN match, historical workspace and run actor, evidence graph, timeline, and coverage gap. Show Muse Spark 1.3 explaining sanitized evidence with evidence-ID citations; the deterministic engine owns status and confidence, the AI is advisory, and invalid output falls back. Show Case B: MULTIPLE_ACTIVE_OWNERS and blocked adoption. Show 12 evidence, 1 gap, SHA-256 checksum, redacted JSON/Markdown export. End with 8 read-only connectors, 7 terminal statuses, 127 tests, and the tagline "Find the owner before you touch the resource." Tone: calm, precise, cinematic-technical. 16:9, 1080p, AI voice, minimal score, burned-in captions. Keep the DEMO / FIXTURE DATA badge visible.
```

---

## Pre-flight checklist before you record

1. **Verify the working demo.** Start the app with `.venv\Scripts\python.exe -m streamlit run app.py`. Run Case A and Case B end to end. Confirm Case A renders `HISTORICAL_OWNER_FOUND` with 12 evidence and Case B renders `MULTIPLE_ACTIVE_OWNERS` with 15 evidence.
2. **Verify Muse Spark is live.** The `.env` must have `AI_ENABLED=true`, `MODEL_API_KEY` set, `META_API_BASE_URL=https://api.meta.ai/v1`, and `META_MODEL=muse-spark-1.3`. Run Case A and confirm the AI Explanation page shows the **Muse Spark** pill, `muse-spark-1.3`, and `Tool calls: 1`. If it shows "Deterministic fallback," fix the API call before recording. Do not fake it.
3. **Warm the model.** Make one AI call before the recorded run so the first-call latency is not in the take. The live call can take 30–90 seconds. Cut or speed-ramp the wait; never show dead air.
4. **Clean the browser.** Use a dedicated browser profile. Hide bookmarks, extensions, notifications, and personal tabs. Set the window to 1920x1080. Hide the Streamlit "Deploy" menu and toolbar in post or configuration.
5. **Clear the session.** Start from a clean session so "Recent investigations" does not show old runs unless you want it to. If you want a populated history, run the cases once before recording and keep the metadata.
6. **Record at 60fps.** 1080p60 gives you clean speed ramps. Use OBS with a high-quality encoder, separate audio tracks, and a 2-second pre-roll.
7. **Record two takes of every click.** One clean take and one safety take. Capture the full progress panel; cut it later.
8. **Capture the terminal proof.** Run `python -m pytest -q` and confirm the current test count. If it is not 127, update the on-screen text and voiceover. Do not show personal paths, API keys, or `.env` contents.
9. **Export the artifacts.** Download the JSON and Markdown reports from Case A. Open them once to confirm the checksum, redaction, and content. Blur local paths if you show the files.
10. **Check the fixture label.** The "DEMO / FIXTURE DATA" badge must be visible in the full-screen shots. If you crop it out, add a persistent lower-third label.
11. **Check the audio.** Record a 10-second test. Listen on phone speakers. If you cannot hear every word, fix it before the full read.
12. **Check the runtime.** Assemble a rough cut first. If it is over 3:00, cut in the order listed above. Do not speed up the voice to fit.

## Production runbook

| Step | Time | Output |
| --- | --- | --- |
| Pre-flight and clean session | 30 min | App verified, Muse Spark verified, browser clean |
| Capture Case A, Case B, report, settings, tests | 45–60 min | 10–12 clean clips, two takes each |
| Generate and review voice | 30 min | Final voice stem, pronunciation checked |
| Assemble and motion graphics | 2–3 hours | Rough cut, graphics, captions |
| Sound design and mix | 45 min | Mixed master |
| QA and export | 30 min | 1080p master, SRT, thumbnail |
| Vertical cut for X | 45 min | 9:16 cut, captions, end card |
| Upload and submit | 20 min | Video link, repo public, submission complete |

## Submission and publishing kit

**Video title:**
GroundTruth — Find the owner before you touch the resource | Meta AI Hackathon 2026

**Description:**
GroundTruth is a read-only AWS resource lineage investigator. Give it a Lambda ARN and it correlates AWS identity, Scalr state and run history, Git commits, CloudTrail events, and CloudWatch activity into one auditable investigation. A deterministic engine owns the status and confidence. Meta Muse Spark explains the evidence, but cannot invent an owner or authorize a change. Built for the Meta Global AI Developer Hackathon 2026.

Demo uses synthetic fixture data. Live connectors are read-only.

**Chapters:**
0:00 The orphaned Lambda
0:18 The investigation
0:36 The finding
1:02 The evidence chain
1:22 Muse Spark: AI explains, engine decides
1:44 The audit bundle
2:00 The duplicate-owner hard stop
2:12 Under the hood
2:28 Why it matters

**Thumbnail:**
The Lineage screen with `HISTORICAL_OWNER_FOUND`, the exact ARN, and the tagline. Maximum 6 words. Keep it readable at 320px wide.

**X / LinkedIn post:**
A production Lambda. No Terraform. No owner.

GroundTruth traces the evidence across AWS, Scalr, Git, CloudTrail, and CloudWatch — and shows exactly where the evidence ends.

Deterministic code owns the status. Muse Spark only explains it.

Built for the Meta Global AI Developer Hackathon 2026.

[link]

#MetaAIHackathon #MuseSpark #PlatformEngineering #AWS #Terraform

## Final note

The video wins on **credibility**, not polish. A judge should finish it thinking:

> "That is a real product, the AI is used in a sophisticated way, and the team understands the failure modes."

If a shot looks generated, if a number is unverifiable, or if the narration claims more than the product does, cut it. The strongest moment in the entire video is not the AI explanation. It is the hard stop: the product refusing to pick a winner.
