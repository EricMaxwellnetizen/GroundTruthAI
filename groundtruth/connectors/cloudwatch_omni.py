from __future__ import annotations

from groundtruth.connectors.base import BaseConnector
from groundtruth.models.connector import ConnectionTest, ConnectorResult
from groundtruth.models.enums import ConnectorStatus
from groundtruth.models.lineage import OmniContext
from groundtruth.utils.urls import safe_url

OMNI_LIMITATION = (
    "CloudWatch Omni is treated as an optional observability companion. "
    "GroundTruth does not invent or call an undocumented Omni REST API; this integration stores only a safe link/context."
)


class CloudWatchOmniConnector(BaseConnector):
    name = "cloudwatch_omni"
    source = "cloudwatch_omni"

    def is_configured(self) -> bool:
        return bool(safe_url(self.settings.cloudwatch_omni_url))

    def test_connection(self) -> ConnectionTest:
        if not self.is_configured():
            return ConnectionTest(
                name="CloudWatch Omni",
                status=ConnectorStatus.NOT_CONFIGURED,
                message="No Omni URL configured. Set CLOUDWATCH_OMNI_URL to a real workspace/space link to enable a handoff link.",
            )
        return ConnectionTest(
            name="CloudWatch Omni",
            status=ConnectorStatus.PARTIAL,
            message="Omni link configured. No public Omni API connector was verified; GroundTruth will show a link and manual context only.",
            details={"url": self.settings.cloudwatch_omni_url, "space": self.settings.cloudwatch_omni_space},
        )

    def get_context(self) -> ConnectorResult:
        if not self.is_configured():
            return self.result(
                ConnectorStatus.NOT_CONFIGURED,
                data=OmniContext(configured=False, limitations=[OMNI_LIMITATION]),
                error="CloudWatch Omni link is not configured.",
            )
        context = OmniContext(
            configured=True,
            url=self.settings.cloudwatch_omni_url,
            space=self.settings.cloudwatch_omni_space or None,
            label=f"CloudWatch Omni{f' · {self.settings.cloudwatch_omni_space}' if self.settings.cloudwatch_omni_space else ''}",
            limitations=[OMNI_LIMITATION],
        )
        return self.result(
            ConnectorStatus.PARTIAL,
            data=context,
            coverage={"url_configured": True, "space_configured": bool(self.settings.cloudwatch_omni_space)},
            warnings=[OMNI_LIMITATION],
        )
