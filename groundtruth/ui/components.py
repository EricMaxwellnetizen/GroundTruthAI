from __future__ import annotations

import html
from datetime import datetime
from typing import Any, Iterable

import streamlit as st

from groundtruth.models.lineage import CoverageRecord, LineageResult
from groundtruth.utils.redaction import safe_text

STATUS_STYLES: dict[str, tuple[str, str]] = {
    "CURRENT_OWNER_FOUND": ("#0F766E", "#D9F3EE"),
    "HISTORICAL_OWNER_FOUND": ("#9A5B13", "#FCEFD8"),
    "MULTIPLE_ACTIVE_OWNERS": ("#B42318", "#FEE4E2"),
    "CANDIDATE_LINEAGE": ("#6B4EFF", "#ECE8FF"),
    "UNATTRIBUTED_IN_CHECKED_SOURCES": ("#475467", "#EAECF0"),
    "INSUFFICIENT_ACCESS": ("#B42318", "#FEE4E2"),
    "IDENTITY_AMBIGUOUS": ("#B42318", "#FEE4E2"),
}
CONFIDENCE_STYLES: dict[str, tuple[str, str]] = {
    "HIGH": ("#0F766E", "#D9F3EE"),
    "MEDIUM": ("#9A5B13", "#FCEFD8"),
    "LOW": ("#6B4EFF", "#ECE8FF"),
    "UNKNOWN": ("#475467", "#EAECF0"),
}
STAGE_LABELS = {
    "fixture": "Fixture",
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
        f'<span style="display:inline-block;padding:0.22rem 0.55rem;border-radius:999px;'
        f"font-size:0.76rem;font-weight:700;letter-spacing:0.02em;color:{foreground};"
        f'background:{background};border:1px solid {foreground}22;">{esc(text, 80)}</span>'
    )


def status_pill(status: str) -> str:
    foreground, background = STATUS_STYLES.get(status, ("#475467", "#EAECF0"))
    return pill(status.replace("_", " ").title(), foreground, background)


def confidence_pill(confidence: str) -> str:
    foreground, background = CONFIDENCE_STYLES.get(confidence, ("#475467", "#EAECF0"))
    return pill(f"{confidence} confidence", foreground, background)


def mode_pill(mode: str) -> str:
    if mode == "fixture":
        return pill("DEMO / FIXTURE DATA", "#9A5B13", "#FCEFD8")
    return pill("LIVE CONNECTORS", "#0F766E", "#D9F3EE")


def inject_css() -> None:
    st.markdown(
        """
<style>
  :root { --gt-ink:#1C1917; --gt-muted:#57534E; --gt-line:#E7E2D8; --gt-paper:#F7F5EF; --gt-teal:#0F766E; }
  .stApp { background: linear-gradient(180deg, #FBF9F4 0%, #F7F5EF 45%, #F4F0E7 100%); }
  .block-container { padding-top: 2rem; max-width: 1320px; }
  [data-testid="stSidebar"] { background:#171A18; width:272px !important; min-width:272px !important; }
  [data-testid="stSidebar"] * { color:#F5F3EC; }
  [data-testid="stSidebar"] .stRadio label { padding:0.22rem 0; }
  [data-testid="stSidebar"] .stRadio label p { white-space:nowrap; font-size:0.92rem; }
  [data-testid="stSidebar"] .stButton > button { color:#171A18 !important; background:#F5F3EC; border:1px solid #57534E; }
  [data-testid="stSidebar"] .stButton > button * { color:#171A18 !important; }
  [data-testid="stSidebar"] code { color:#171A18 !important; background:#E9E4D8; }
  [data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color:#C9C4B8; }
  [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color:#F5F3EC; }
  h1, h2, h3 { font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif; letter-spacing:-0.02em; color:var(--gt-ink); }
  .gt-hero { border:1px solid var(--gt-line); border-radius:22px; padding:1.4rem 1.5rem 1.2rem; background:
    radial-gradient(circle at 92% 8%, #CDEDE5 0, transparent 30%),
    radial-gradient(circle at 5% 100%, #F4DFC0 0, transparent 34%), #FFFDF8; margin-bottom:1rem; }
  .gt-hero h1 { font-size:2.35rem; margin:0.25rem 0 0.4rem; }
  .gt-hero p { color:var(--gt-muted); max-width: 820px; margin:0; font-size:1.02rem; }
  .gt-kicker { font-size:0.72rem; font-weight:800; letter-spacing:0.16em; color:var(--gt-teal); text-transform:uppercase; }
  .gt-card { border:1px solid var(--gt-line); border-radius:16px; padding:1rem 1.05rem; background:#FFFDF8; }
  .gt-card h4 { margin:0 0 0.35rem; font-size:0.95rem; }
  .gt-card p { margin:0; color:var(--gt-muted); font-size:0.88rem; }
  .gt-metric { border:1px solid var(--gt-line); border-radius:16px; padding:0.85rem 0.95rem; background:#FFFDF8; min-height:86px; }
  .gt-metric .value { font-size:1.45rem; font-weight:800; color:var(--gt-ink); }
  .gt-metric .label { font-size:0.78rem; color:var(--gt-muted); text-transform:uppercase; letter-spacing:0.06em; }
  .gt-banner { border-radius:14px; padding:0.85rem 1rem; border:1px solid #E7C98E; background:#FFF6E4; color:#6B4710; font-size:0.9rem; margin:0.5rem 0 1rem; }
  .gt-empty { border:1px dashed #CDC7BA; border-radius:18px; padding:2rem 1.3rem; text-align:center; color:var(--gt-muted); background:#FFFDF8; }
  .gt-empty strong { display:block; color:var(--gt-ink); font-size:1.05rem; margin-bottom:0.3rem; }
  .gt-chip { display:inline-block; margin:0.12rem 0.22rem 0.12rem 0; padding:0.18rem 0.48rem; border-radius:999px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size:0.72rem; color:#155E56; background:#E9F6F1; border:1px solid #B9E1D6; }
  .gt-source { display:inline-block; margin-right:0.4rem; color:#57534E; font-size:0.78rem; }
  .gt-rule { height:1px; background:var(--gt-line); margin:1rem 0; border:0; }
  .gt-mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size:0.82rem; }
  .stButton > button { border-radius:10px; font-weight:650; }
  .stDownloadButton > button { border-radius:10px; font-weight:650; }
  div[data-testid="stDataFrame"] { border:1px solid var(--gt-line); border-radius:14px; overflow:hidden; }
</style>
        """,
        unsafe_allow_html=True,
    )


def header(kicker: str, title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="gt-hero"><div class="gt-kicker">{esc(kicker, 80)}</div>'
        f"<h1>{esc(title, 180)}</h1><p>{esc(subtitle, 420)}</p></div>",
        unsafe_allow_html=True,
    )


def section(title: str, subtitle: str | None = None) -> None:
    st.markdown(f"### {esc(title, 180)}")
    if subtitle:
        st.caption(safe_text(subtitle, limit=500))


def metric(label: str, value: str, help_text: str | None = None) -> None:
    hint = f'<div class="gt-metric"><div class="value">{esc(value, 80)}</div><div class="label">{esc(label, 80)}</div></div>'
    st.markdown(hint, unsafe_allow_html=True)
    if help_text:
        st.caption(help_text)


def empty_state(title: str, message: str) -> None:
    st.markdown(
        f'<div class="gt-empty"><strong>{esc(title, 160)}</strong>{esc(message, 500)}</div>',
        unsafe_allow_html=True,
    )


def fixture_banner(fixture: bool, mode: str | None = None) -> None:
    if fixture or mode == "fixture":
        st.markdown(
            '<div class="gt-banner"><strong>Demo mode.</strong> Every record on this screen is synthetic fixture data. '
            "No live AWS account, Scalr workspace, GitLab project, or CloudTrail event was queried.</div>",
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
