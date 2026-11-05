# GroundTruth — 3-minute live demo (judge-proof)

Runs fully offline in the simulated Northgate Production mirror; every step also works live.
Rehearse once with `streamlit run app.py`. Total: ~3:00. Fallbacks noted per step — nothing here can dead-end.

## Script

**0:00 — Problem (Overview).** "A Lambda is running in production. Nobody can find its owner. Guessing wrong means fighting state or deleting the wrong thing. GroundTruth finds the evidence before you touch the resource." Point at the fleet KPIs and *Needs attention* list. *(Meta beat: "The AI explains. Deterministic code decides.")*

**0:25 — Investigate (Case A).** Click **Open investigation: A — Historical owner found**. While stages run: "AWS identity, Scalr state history, the run, its exact Git commit, CloudTrail, CloudWatch — correlated by exact ARN, never by name similarity."

**0:50 — Verdict (Lineage overview).** "Historical owner found, high confidence — and the UI shows *why*: workspace `prod-orders`, state version, run actor, verified commit SHA. Note the three different identities — run actor, Git author, CloudTrail principal. GroundTruth never collapses them into 'the creator'." Scroll to **Adoption proposal**: "A reviewable import block, generated deterministically." Open **Action Center**: "Reattribute or retire — planned, typed confirmation, audit-logged."

**1:35 — Proof (Evidence graph + Timeline).** "Every edge carries an evidence ID. Solid is exact, dotted is candidate. Click any node — it traces to the source record." *(Fallback: tables under the graph show the same data.)*

**1:55 — Meta AI (AI explanation).** "Muse Spark explains the same evidence. Every fact cites an evidence ID — the backend validates them; invent one and it's rejected. With no key, you get this deterministic fallback instead — the product never depends on the model." If a key is configured, click **Regenerate explanation** and show `muse-spark-1.3` + tool calls. Mention: "Or bring your own Llama open-weights endpoint — same guarantees."

**2:25 — Safety (Case B).** Open **B — Multiple active owners**. "Two workspaces claim the same ARN. Adoption is hard-blocked. This refusal is the feature — it's what stops a duplicate-state outage." Try Delete in the Action Center and show the block reason.

**2:45 — Close (Overview + Report).** Run the **automation sweep**: "Historical owners get reattributions prepared automatically; disputes queue for humans." Open **Evidence report**, download the bundle: "Checksummed, redacted, portable. GroundTruth: find the owner before you touch the resource."

## If something misbehaves live

- Model slow/unavailable → the deterministic fallback is already on screen; narrate it as designed behavior.
- Clicks lag → stay on the current page and use its tables; every page renders the same investigation.
- Asked "is this real data?" → "Simulated tenant, production payload formats — deliberately, so you can verify the logic. Live mode connects from Settings with pasted credentials; the code paths are identical."
