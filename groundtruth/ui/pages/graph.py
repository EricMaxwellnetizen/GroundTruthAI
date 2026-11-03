from __future__ import annotations

import math

import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from groundtruth.models.graph import EvidenceGraph
from groundtruth.ui import components as ui
from groundtruth.ui import state

NODE_COLORS = {
    "aws_lambda_function": "#0F766E",
    "scalr_workspace": "#B45309",
    "scalr_resource_usage": "#D97706",
    "scalr_run": "#7C3AED",
    "scalr_state_version": "#8B5CF6",
    "git_repository": "#2563EB",
    "git_commit": "#3B82F6",
    "git_file": "#60A5FA",
    "cloudtrail_event": "#B42318",
    "cloudwatch_activity": "#0891B2",
    "actor": "#57534E",
}


def _label(value: str, limit: int = 28) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def build_figure(graph: EvidenceGraph, show_inferred: bool) -> go.Figure:
    graph_data = nx.DiGraph()
    for node in graph.nodes:
        graph_data.add_node(node.node_id)
    for edge in graph.edges:
        if edge.inferred and not show_inferred:
            continue
        graph_data.add_edge(edge.source_node, edge.target_node, edge=edge)
    if graph_data.number_of_nodes() == 0:
        return go.Figure()
    positions = nx.spring_layout(
        graph_data, seed=42, k=1.35 / math.sqrt(max(graph_data.number_of_nodes(), 1)), iterations=120
    )
    by_type: dict[str, list] = {}
    for node in graph.nodes:
        if node.node_id not in positions:
            continue
        by_type.setdefault(node.node_type, []).append(node)

    figure = go.Figure()
    for node_type, nodes in sorted(by_type.items()):
        color = NODE_COLORS.get(node_type, "#475467")
        figure.add_trace(
            go.Scatter(
                x=[positions[node.node_id][0] for node in nodes],
                y=[positions[node.node_id][1] for node in nodes],
                mode="markers+text",
                name=node_type.replace("_", " "),
                text=[_label(node.label) for node in nodes],
                textposition="bottom center",
                textfont=dict(size=9, color="#1C1917"),
                marker=dict(
                    size=22 if node_type == "aws_lambda_function" else 15,
                    color=color,
                    line=dict(width=1.2, color="#FFFDF8"),
                ),
                customdata=[[node.source_evidence_id or "no evidence", str(node.attributes)] for node in nodes],
                hovertemplate="<b>%{text}</b><br>Type: "
                + node_type.replace("_", " ")
                + "<br>Evidence: %{customdata[0]}<extra></extra>",
            )
        )

    for inferred, dash, color, width in ((False, "solid", "#57534E", 1.6), (True, "dot", "#8A7F70", 1.2)):
        edge_x: list[float | None] = []
        edge_y: list[float | None] = []
        for edge in graph.edges:
            if edge.inferred != inferred:
                continue
            if edge.source_node not in positions or edge.target_node not in positions:
                continue
            start = positions[edge.source_node]
            end = positions[edge.target_node]
            edge_x.extend([start[0], end[0], None])
            edge_y.extend([start[1], end[1], None])
        if edge_x:
            figure.add_trace(
                go.Scatter(
                    x=edge_x,
                    y=edge_y,
                    mode="lines",
                    line=dict(width=width, color=color, dash=dash),
                    hoverinfo="skip",
                    name="Inferred / candidate" if inferred else "Exact match",
                    legendgroup="edges",
                )
            )

    figure.update_layout(
        height=620,
        margin=dict(l=20, r=20, t=30, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        legend=dict(orientation="h", yanchor="bottom", y=-0.08, x=0),
        hovermode="closest",
    )
    return figure


def render() -> None:
    result = state.current_result()
    if result is None:
        ui.header("Evidence graph", "Follow the path from Lambda to workspace.", "")
        ui.empty_state("No investigation loaded", "Run a fixture case to build its evidence graph.")
        return
    ui.header(
        "Evidence graph",
        "Every edge carries a citation.",
        "Solid edges are exact identifier matches. Dotted edges are inferred or candidate links and never establish ownership by themselves.",
    )
    ui.fixture_banner(result.fixture, result.mode)
    graph = result.graph
    col1, col2 = st.columns(2)
    with col1:
        show_inferred = st.checkbox("Show candidate / inferred edges", value=True, key="graph_inferred")
    with col2:
        types = sorted({node.node_type for node in graph.nodes})
        selected_types = st.multiselect("Node types", types, default=types, key="graph_types")
    filtered = EvidenceGraph(
        nodes=[node for node in graph.nodes if node.node_type in selected_types],
        edges=[
            edge
            for edge in graph.edges
            if edge.source_node in {node.node_id for node in graph.nodes if node.node_type in selected_types}
            and edge.target_node in {node.node_id for node in graph.nodes if node.node_type in selected_types}
        ],
    )
    if not filtered.nodes:
        ui.empty_state("Nothing to display", "Select at least one node type.")
        return
    st.plotly_chart(build_figure(filtered, show_inferred), width="stretch", config={"displayModeBar": False})
    st.caption(
        f"{len(filtered.nodes)} nodes · {len(filtered.edges)} edges · {sum(1 for edge in filtered.edges if edge.inferred)} inferred. "
        "Hover a node to see its evidence ID."
    )
    with st.expander("Graph node and edge tables", expanded=False):
        st.markdown("**Nodes**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "ID": node.node_id,
                        "Type": node.node_type,
                        "Label": node.label,
                        "Evidence": node.source_evidence_id or "",
                        "Fixture": node.fixture,
                    }
                    for node in filtered.nodes
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        st.markdown("**Edges**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "From": edge.source_node,
                        "To": edge.target_node,
                        "Label": edge.label,
                        "Match": edge.match_type.value,
                        "Confidence": edge.confidence.value,
                        "Inferred": edge.inferred,
                        "Evidence": edge.source_evidence_id,
                        "Observed": edge.observed_at.isoformat(timespec="seconds"),
                    }
                    for edge in filtered.edges
                ]
            ),
            hide_index=True,
            width="stretch",
        )
