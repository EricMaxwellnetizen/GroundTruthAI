from __future__ import annotations

import html
from datetime import datetime
from typing import Any, Iterable

import streamlit as st

from groundtruth.models.lineage import CoverageRecord, LineageResult
from groundtruth.utils.redaction import safe_text

STATUS_STYLES: dict[str, tuple[str, str, str]] = {
    "CURRENT_OWNER_FOUND": ("#067647", "#ECFDF3", "Active owner"),
    "HISTORICAL_OWNER_FOUND": ("#B54708", "#FFFAEB", "Historical owner"),
    "MULTIPLE_ACTIVE_OWNERS": ("#B42318", "#FEF3F2", "Ownership conflict"),
    "CANDIDATE_LINEAGE": ("#363F72", "#EEF4FF", "Candidate"),
    "UNATTRIBUTED_IN_CHECKED_SOURCES": ("#475467", "#F2F4F7", "Unattributed"),
    "INSUFFICIENT_ACCESS": ("#B42318", "#FEF3F2", "Access required"),
    "IDENTITY_AMBIGUOUS": ("#B42318", "#FEF3F2", "Ambiguous identity"),
}
CONFIDENCE_STYLES: dict[str, tuple[str, str]] = {
    "HIGH": ("#067647", "#ECFDF3"),
    "MEDIUM": ("#B54708", "#FFFAEB"),
    "LOW": ("#363F72", "#EEF4FF"),
    "UNKNOWN": ("#475467", "#F2F4F7"),
}
STAGE_LABELS = {
    "fixture": "Environment",
    "aws_lambda": "AWS",
    "scalr": "Scalr",
    "git": "Git",
    "cloudtrail": "CloudTrail",
    "cloudwatch": "CloudWatch",
    "cloudwatch_omni": "Omni",
    "correlation": "Correlation",
    "ai": "Muse Spark",
    "export": "Export",
}


def esc(value: Any, limit: int = 600) -> str:
    return html.escape(safe_text(str(value if value is not None else ""), limit=limit))


def pill(text: str, foreground: str, background: str) -> str:
    return (
        f'<span style="display:inline-flex;align-items:center;gap:0.35rem;padding:0.2rem 0.6rem;border-radius:999px;'
        f"font-size:0.72rem;font-weight:600;letter-spacing:0.01em;color:{foreground};"
        f'background:{background};border:1px solid {foreground}30;white-space:nowrap;">'
        f'<span style="width:6px;height:6px;border-radius:50%;background:{foreground};display:inline-block;"></span>'
        f"{esc(text, 80)}</span>"
    )


def status_pill(status: str) -> str:
    foreground, background, label = STATUS_STYLES.get(status, ("#475467", "#F2F4F7", status.replace("_", " ").title()))
    return pill(label, foreground, background)


def status_label(status: str) -> str:
    return STATUS_STYLES.get(status, ("#475467", "#F2F4F7", status.replace("_", " ").title()))[2]


def confidence_pill(confidence: str) -> str:
    foreground, background = CONFIDENCE_STYLES.get(confidence, ("#475467", "#F2F4F7"))
    return pill(f"{confidence.title()} confidence", foreground, background)


def mode_pill(mode: str) -> str:
    if mode == "fixture":
        return pill("Simulated environment", "#B54708", "#FFFAEB")
    return pill("Live environment", "#067647", "#ECFDF3")


def inject_css() -> None:
    st.markdown(
        """
<style>
  :root {
    --gt-ink:#0F172A; --gt-muted:#64748B; --gt-faint:#94A3B8; --gt-line:#E2E8F0;
    --gt-bg:#F6F7F9; --gt-card:#FFFFFF; --gt-accent:#0F766E; --gt-accent-soft:#E6F4F1;
    --gt-navy:#0B1526;
  }
  .stApp { background: var(--gt-bg); }
  [data-testid="stAppDeployButton"], .stDeployButton, [data-testid="stDeployButton"] { display: none !important; visibility: hidden !important; }
  .block-container { padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1360px; }
  [data-testid="stSidebar"] { background: var(--gt-navy); width: 264px !important; min-width: 264px !important; border-right: 1px solid #1E293B; }
  [data-testid="stSidebar"] * { color: #E2E8F0; }
  [data-testid="stSidebar"] .stRadio label { padding: 0.14rem 0.4rem; border-radius: 8px; }
  [data-testid="stSidebar"] .stRadio label:hover { background: #16213A; }
  [data-testid="stSidebar"] .stRadio label p { white-space: nowrap; font-size: 0.88rem; color: #CBD5E1; }
  [data-testid="stSidebar"] .stButton > button { color: #0F172A !important; background: #F1F5F9; border: 1px solid #334155; border-radius: 8px; }
  [data-testid="stSidebar"] .stButton > button * { color: #0F172A !important; }
  [data-testid="stSidebar"] code { color: #E2E8F0 !important; background: #1E293B; border: 1px solid #334155; }
  [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color: #94A3B8 !important; font-size: 0.76rem; line-height: 1.45; }
  [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: #E2E8F0; }
  [data-testid="stSidebar"] hr { border-color: #1E293B; }
  h1, h2, h3 { font-family: Inter, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; letter-spacing: -0.02em; color: var(--gt-ink); font-weight: 700; }
  h3 { font-size: 1.02rem; }
  p, li, label { font-family: Inter, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
  .gt-eyebrow { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.14em; color: var(--gt-accent); text-transform: uppercase; margin-bottom: 0.35rem; }
  .gt-pagehead { margin-bottom: 1.1rem; }
  .gt-pagehead h1 { font-size: 1.65rem; line-height: 1.2; margin: 0 0 0.35rem; font-weight: 750; }
  .gt-pagehead .gt-sub { color: var(--gt-muted); font-size: 0.92rem; line-height: 1.55; max-width: 860px; margin: 0; }
  .gt-pagehead .gt-crumb { color: var(--gt-faint); font-size: 0.76rem; margin-bottom: 0.45rem; }
  .gt-card { border: 1px solid var(--gt-line); border-radius: 12px; padding: 1rem 1.1rem; background: var(--gt-card); box-shadow: 0 1px 2px rgba(15,23,42,0.04); }
  .gt-card h4 { margin: 0 0 0.3rem; font-size: 0.88rem; font-weight: 700; color: var(--gt-ink); }
  .gt-card p { margin: 0; color: var(--gt-muted); font-size: 0.84rem; line-height: 1.55; }
  .gt-stat { border: 1px solid var(--gt-line); border-radius: 12px; padding: 0.9rem 1rem; background: var(--gt-card); box-shadow: 0 1px 2px rgba(15,23,42,0.04); border-top: 3px solid var(--gt-accent); min-height: 92px; }
  .gt-stat .value { font-size: 1.5rem; font-weight: 750; color: var(--gt-ink); line-height: 1.15; letter-spacing: -0.02em; }
  .gt-stat .label { font-size: 0.7rem; color: var(--gt-muted); text-transform: uppercase; letter-spacing: 0.08em; font-weight: 650; margin-top: 0.2rem; }
  .gt-stat .hint { font-size: 0.76rem; color: var(--gt-faint); margin-top: 0.25rem; line-height: 1.4; }
  .gt-metric { border: 1px solid var(--gt-line); border-radius: 12px; padding: 0.85rem 0.95rem; background: var(--gt-card); min-height: 86px; }
  .gt-metric .value { font-size: 1.35rem; font-weight: 750; color: var(--gt-ink); }
  .gt-metric .label { font-size: 0.72rem; color: var(--gt-muted); text-transform: uppercase; letter-spacing: 0.07em; font-weight: 650; }
  .gt-env { display:flex; gap:0.6rem; align-items:flex-start; border-radius: 10px; padding: 0.7rem 0.9rem; border: 1px solid #FEDF89; background: #FFFAEB; color: #7A2E0E; font-size: 0.83rem; line-height: 1.5; margin: 0 0 1rem; }
  .gt-env strong { color: #93370D; }
  .gt-empty { border: 1px dashed #CBD5E1; border-radius: 12px; padding: 2rem 1.3rem; text-align: center; color: var(--gt-muted); background: var(--gt-card); }
  .gt-empty strong { display: block; color: var(--gt-ink); font-size: 0.98rem; margin-bottom: 0.3rem; }
  .gt-chip { display: inline-block; margin: 0.12rem 0.22rem 0.12rem 0; padding: 0.18rem 0.5rem; border-radius: 6px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.7rem; color: #0B4F4A; background: var(--gt-accent-soft); border: 1px solid #99D5CC; }
  .gt-source { display: inline-block; margin-right: 0.4rem; color: var(--gt-muted); font-size: 0.76rem; }
  .gt-rule { height: 1px; background: var(--gt-line); margin: 1.2rem 0 0.6rem; border: 0; }
  .gt-mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.8rem; }
  .gt-kv { font-size: 0.82rem; color: var(--gt-muted); line-height: 1.7; }
  .stButton > button { border-radius: 8px; font-weight: 600; font-size: 0.86rem; }
  .stDownloadButton > button { border-radius: 8px; font-weight: 600; font-size: 0.86rem; }
  div[data-testid="stDataFrame"] { border: 1px solid var(--gt-line); border-radius: 10px; overflow: hidden; }
  [data-testid="stMetricValue"] { font-size: 1.15rem; }
  div[data-testid="stExpander"] { border-radius: 10px; }
</style>
        """,
        unsafe_allow_html=True,
    )


def header(kicker: str, title: str, subtitle: str) -> None:
    sub = f'<p class="gt-sub">{esc(subtitle, 420)}</p>' if subtitle else ""
    st.markdown(
        f'<div class="gt-pagehead"><div class="gt-eyebrow">{esc(kicker, 80)}</div>'
        f"<h1>{esc(title, 180)}</h1>{sub}</div>",
        unsafe_allow_html=True,
    )


def section(title: str, subtitle: str | None = None) -> None:
    st.markdown(f"### {esc(title, 180)}")
    if subtitle:
        st.caption(safe_text(subtitle, limit=500))


def metric(label: str, value: str, help_text: str | None = None) -> None:
    hint = f'<div class="hint">{esc(help_text, 200)}</div>' if help_text else ""
    st.markdown(
        f'<div class="gt-stat"><div class="value">{esc(value, 80)}</div><div class="label">{esc(label, 80)}</div>{hint}</div>',
        unsafe_allow_html=True,
    )


def empty_state(title: str, message: str) -> None:
    st.markdown(
        f'<div class="gt-empty"><strong>{esc(title, 160)}</strong>{esc(message, 500)}</div>',
        unsafe_allow_html=True,
    )


def fixture_banner(fixture: bool, mode: str | None = None) -> None:
    if fixture or mode == "fixture":
        st.markdown(
            '<div class="gt-env"><span style="font-size:0.95rem;">&#9679;</span><div>'
            "<strong>Simulated environment &mdash; Northgate Production (mirror).</strong> "
            "Responses mirror live AWS, Scalr, GitLab, CloudTrail and CloudWatch payloads so the full investigation flow can be reviewed end to end. "
            "Connect live credentials in Settings to investigate a real account.</div></div>",
            unsafe_allow_html=True,
        )


def evidence_chips(evidence_ids: Iterable[str], *, result: LineageResult | None = None, limit: int = 12) -> None:
    ids = [str(item) for item in evidence_ids][:limit]
    if not ids:
        st.caption("No evidence citations.")
        return
    labels = []
    for evidence_id in ids:
        evidence = result.evidence_by_id(evidence_id) if result else None
        title = f"{evidence_id}"
        if evidence:
            title = f"{evidence_id} · {evidence.source_label}"
        labels.append(f'<span class="gt-chip" title="{esc(title, 200)}">{esc(evidence_id, 80)}</span>')
    st.markdown("".join(labels), unsafe_allow_html=True)


def source_badge(source: str) -> str:
    return f'<span class="gt-source"><strong>{esc(source.replace("_", " "), 80)}</strong></span>'


def format_dt(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def coverage_gap_summary(result: LineageResult) -> list[CoverageRecord]:
    return result.coverage_gaps()
