from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.models.enums import LineageStatus
from groundtruth.models.lineage import LineageResult

BLOCKED_STATUSES = {
    LineageStatus.MULTIPLE_ACTIVE_OWNERS,
    LineageStatus.IDENTITY_AMBIGUOUS,
    LineageStatus.INSUFFICIENT_ACCESS,
}


class AdoptionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eligible: bool
    blocked_reason: str | None = None
    function_name: str
    resource_address: str
    import_id: str
    hcl: str
    checklist: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _label(name: str) -> str:
    label = re.sub(r"[^a-zA-Z0-9_]", "_", name).strip("_").lower()
    if not label or label[0].isdigit():
        label = f"fn_{label}"
    return label


def build_adoption_proposal(result: LineageResult) -> AdoptionProposal:
    resource = result.resource
    label = _label(resource.name)
    address = f"aws_lambda_function.{label}"
    import_id = resource.arn or resource.name
    evidence_ids = list(result.recommendation.evidence_ids)
    warnings = [
        "Preview only. GroundTruth never runs terraform apply, tofu apply, or any state mutation.",
        "Import blocks require Terraform >= 1.5 or a compatible OpenTofu release; verify against your pinned version.",
    ]
    if result.status in BLOCKED_STATUSES:
        reason = {
            LineageStatus.MULTIPLE_ACTIVE_OWNERS: "Duplicate active ownership must be resolved before any adoption proposal can be used.",
            LineageStatus.IDENTITY_AMBIGUOUS: "The resource identity is ambiguous; supply a verified ARN, account and region first.",
            LineageStatus.INSUFFICIENT_ACCESS: "A required source could not be read; ownership is unknown and adoption would be a guess.",
        }[result.status]
        return AdoptionProposal(
            eligible=False,
            blocked_reason=reason,
            function_name=resource.name,
            resource_address=address,
            import_id=import_id,
            hcl="",
            checklist=[],
            evidence_ids=evidence_ids,
            warnings=warnings,
        )
    if result.current_owners:
        owner = result.current_owners[0]
        warnings.append(
            f"This function is already managed by workspace {owner.workspace.name} at {owner.resource_address}. "
            "The block below is for reference reconciliation only — do not import it into a second workspace."
        )
    runtime = resource.safe_attributes.get("runtime") or "python3.13"
    handler = resource.safe_attributes.get("handler") or "app.handler"
    memory = resource.safe_attributes.get("memory_size") or 512
    timeout = resource.safe_attributes.get("timeout") or 30
    role = resource.safe_attributes.get("role") or f"arn:aws:iam::{resource.account_id}:role/<execution-role>"
    tags = resource.tags or {}
    tag_lines = "".join(f'    {key} = "{value}"\n' for key, value in sorted(tags.items()))
    hcl = (
        f"# GroundTruth adoption preview for {resource.name} ({resource.region})\n"
        f"# Status: {result.status.value} · Confidence: {result.confidence.value}\n"
        "# Review in version control. Run plan in an isolated sandbox before any apply.\n\n"
        f'resource "aws_lambda_function" "{label}" {{\n'
        f'  function_name = "{resource.name}"\n'
        f'  role          = "{role}"\n'
        f'  runtime       = "{runtime}"\n'
        f'  handler       = "{handler}"\n'
        f"  memory_size   = {memory}\n"
        f"  timeout       = {timeout}\n"
    )
    if tag_lines:
        hcl += "\n  tags = {\n" + tag_lines + "  }\n"
    hcl += f'}}\n\nimport {{\n  to = aws_lambda_function.{label}\n  id = "{import_id}"\n}}\n'
    checklist = [
        "Confirm the owning team and cost centre from the investigation evidence.",
        "Create the resource block in the target root module and commit it on a branch.",
        "Run terraform plan (or tofu plan) in an isolated sandbox with read-only credentials first, then with the import block.",
        "Verify the plan shows only the expected import — no creates, replacements or deletions.",
        "Obtain a second reviewer approval before applying; GroundTruth does not apply changes.",
        "Re-run this investigation after adoption and confirm exactly one active owner remains.",
    ]
    return AdoptionProposal(
        eligible=True,
        function_name=resource.name,
        resource_address=address,
        import_id=import_id,
        hcl=hcl,
        checklist=checklist,
        evidence_ids=evidence_ids,
        warnings=warnings,
    )
