from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.models.connector import utc_now
from groundtruth.models.enums import ConfidenceLabel, MatchType


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    node_type: str
    label: str
    source_evidence_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    fixture: bool = False


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge_id: str
    source_node: str
    target_node: str
    edge_type: str
    label: str
    source_evidence_id: str
    observed_at: datetime = Field(default_factory=utc_now)
    match_type: MatchType
    confidence: ConfidenceLabel = ConfidenceLabel.UNKNOWN
    inferred: bool = False
    fixture: bool = False


class EvidenceGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    def add_node(self, node: GraphNode) -> None:
        if not any(existing.node_id == node.node_id for existing in self.nodes):
            self.nodes.append(node)

    def add_edge(self, edge: GraphEdge) -> None:
        if not any(existing.edge_id == edge.edge_id for existing in self.edges):
            self.edges.append(edge)
