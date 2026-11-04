# Policies

This directory contains reference infrastructure policy, not executable application policy.

- `aws-read-only-policy.json` is the least-privilege AWS policy used by the live connectors. It grants read-only Lambda, IAM role metadata, CloudTrail, CloudWatch, and STS identity access. It grants no invoke, update, delete, code download, or IAM mutation permission.

## Adoption policy

Adoption decisions are enforced inside the deterministic lineage engine rather than in a separate policy module. `Recommendation.blocked_adoption` is set by fixed rules in `groundtruth/services/lineage_engine.py`:

- multiple active exact owners -> adoption blocked;
- historical-only ownership -> no current-owner recommendation;
- insufficient access -> request permission, never guess an owner;
- candidate-only lineage -> manual review, never an automatic adoption.

The AI layer cannot change these values. A separate `policies/adoption.py` module is intentionally omitted to avoid a second, divergent source of truth.
