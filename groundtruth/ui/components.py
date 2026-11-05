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
    --gt-ink:#0B1220; --gt-muted:#5B6B82; --gt-faint:#8CA0B8; --gt-line:#E3EAF2;
    --gt-bg:#F4F7FA; --gt-card:#FFFFFF; --gt-teal:#0F766E; --gt-cyan:#06B6D4;
    --gt-grad: linear-gradient(120deg,#0F766E 0%,#0891B2 55%,#06B6D4 100%);
  }
  html { scroll-behavior:smooth; }
  ::-webkit-scrollbar { width:10px; height:10px; }
  ::-webkit-scrollbar-thumb { background:#C7D3E0; border-radius:8px; border:2px solid var(--gt-bg); }
  .stApp {
    background:
      radial-gradient(900px 420px at 88% -80px, rgba(6,182,212,.14), transparent 60%),
      radial-gradient(700px 380px at -120px 30%, rgba(15,118,110,.10), transparent 55%),
      var(--gt-bg);
  }
  .block-container { padding-top: 1.5rem; padding-bottom: 2.2rem; max-width: 1380px; }
  [data-testid="stSidebar"] {
    background: linear-gradient(180deg,#081120 0%,#0B1B31 58%,#0A2436 100%);
    width: 268px !important; min-width: 268px !important; border-right: 1px solid rgba(103,232,249,.14);
    box-shadow: 12px 0 32px rgba(2,12,27,.18);
  }
  [data-testid="stSidebar"] * { color: #E2E8F0; }
  [data-testid="stSidebar"] .stRadio div[role="radiogroup"] { gap: 2px; }
  [data-testid="stSidebar"] .stRadio label {
    padding: 0.42rem 0.65rem; border-radius: 10px; border: 1px solid transparent; transition: all .15s ease;
  }
  [data-testid="stSidebar"] .stRadio label:hover { background: rgba(148,197,255,.08); }
  [data-testid="stSidebar"] .stRadio label:has(input:checked) {
    background: linear-gradient(120deg, rgba(15,118,110,.38), rgba(6,182,212,.22));
    border-color: rgba(103,232,249,.35); box-shadow: 0 4px 14px rgba(6,182,212,.12);
  }
  [data-testid="stSidebar"] .stRadio label p { white-space: nowrap; font-size: 0.88rem; color: #CBD5E1; font-weight: 550; }
  [data-testid="stSidebar"] .stRadio label:has(input:checked) p { color:#FFFFFF; font-weight:700; }
  [data-testid="stSidebar"] .stButton > button { color: #081120 !important; background:#E0F2FE; border:0; border-radius:10px; font-weight:700; }
  [data-testid="stSidebar"] .stButton > button * { color: #081120 !important; }
  [data-testid="stSidebar"] code { color: #A5F3FC !important; background: rgba(8,47,73,.65); border: 1px solid rgba(103,232,249,.25); }
  [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color: #8CA0B8 !important; font-size: 0.76rem; line-height: 1.5; }
  [data-testid="stSidebar"] hr { border-color: rgba(148,197,255,.12); }
  h1, h2, h3 { font-family: Inter,-apple-system,"Segoe UI",Roboto,Arial,sans-serif; letter-spacing:-0.025em; color:var(--gt-ink); }
  h3 { font-size: 1.06rem; font-weight: 750; margin-top: 1.4rem; }
  p, li, label, .stMarkdown { font-family: Inter,-apple-system,"Segoe UI",Roboto,Arial,sans-serif; }
  .gt-eyebrow { display:flex; align-items:center; gap:.55rem; font-size:.68rem; font-weight:800; letter-spacing:.16em; color:var(--gt-teal); text-transform:uppercase; margin-bottom:.4rem; }
  .gt-eyebrow::before { content:""; width:26px; height:3px; border-radius:99px; background:var(--gt-grad); display:inline-block; }
  .gt-pagehead { margin-bottom: 1.15rem; position:relative; }
  .gt-pagehead h1 {
    font-size: 2rem; line-height:1.12; margin:0 0 .4rem; font-weight:850;
    background: linear-gradient(100deg,#0B1220 55%,#0E7490 100%); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent;
  }
  .gt-pagehead .gt-sub { color:var(--gt-muted); font-size:.94rem; line-height:1.6; max-width:880px; margin:0; }
  .gt-card, .gt-stat, .gt-metric, .gt-empty {
    background: rgba(255,255,255,.94); border:1px solid var(--gt-line); border-radius:16px;
    box-shadow: 0 1px 2px rgba(11,18,32,.05), 0 10px 28px -18px rgba(11,18,32,.22);
  }
  .gt-card { padding: 1.05rem 1.15rem; }
  .gt-card h4 { margin:0 0 .3rem; font-size:.9rem; font-weight:750; }
  .gt-card p { margin:0; color:var(--gt-muted); font-size:.85rem; line-height:1.6; }
  div[data-testid="stVerticalBlockBorderWrapper"] { border-radius:16px !important; box-shadow: 0 1px 2px rgba(11,18,32,.05), 0 12px 30px -20px rgba(11,18,32,.25); }
  .gt-stat { padding: 1rem 1.05rem; min-height: 96px; position:relative; overflow:hidden; }
  .gt-stat::before { content:""; position:absolute; inset:0 0 auto 0; height:3px; background:var(--gt-grad); }
  .gt-stat .value { font-size:1.7rem; font-weight:850; line-height:1.1; letter-spacing:-0.03em; }
  .gt-stat .label { font-size:.68rem; color:var(--gt-muted); text-transform:uppercase; letter-spacing:.09em; font-weight:700; margin-top:.25rem; }
  .gt-stat .hint { font-size:.76rem; color:var(--gt-faint); margin-top:.3rem; line-height:1.45; }
  .gt-metric { padding:.9rem 1rem; min-height:88px; }
  .gt-metric .value { font-size:1.4rem; font-weight:800; }
  .gt-metric .label { font-size:.7rem; color:var(--gt-muted); text-transform:uppercase; letter-spacing:.08em; font-weight:700; }
  .gt-env { display:flex; gap:.6rem; align-items:flex-start; border-radius:12px; padding:.72rem .95rem; border:1px solid rgba(217,164,65,.45);
    background: linear-gradient(120deg, rgba(255,250,235,.97), rgba(254,243,199,.78)); color:#7A2E0E; font-size:.83rem; line-height:1.55; margin:0 0 1rem;
    box-shadow: 0 8px 22px -16px rgba(146,64,14,.5); }
  .gt-env strong { color:#93370D; }
  .gt-empty { border-style:dashed; padding:2rem 1.3rem; text-align:center; color:var(--gt-muted); }
  .gt-empty strong { display:block; color:var(--gt-ink); font-size:.98rem; margin-bottom:.3rem; }
  .gt-chip { display:inline-block; margin:.12rem .22rem .12rem 0; padding:.18rem .5rem; border-radius:7px; font-family:ui-monospace,Menlo,Consolas,monospace;
    font-size:.7rem; color:#075E57; background:linear-gradient(120deg,#E6F7F3,#E0F5FB); border:1px solid #A7E3D8; }
  .gt-source { display:inline-block; margin-right:.4rem; color:var(--gt-muted); font-size:.76rem; }
  .gt-rule { height:1px; background:linear-gradient(90deg,transparent,var(--gt-line),transparent); margin:1.3rem 0 .6rem; border:0; }
  .gt-mono { font-family:ui-monospace,Menlo,Consolas,monospace; font-size:.8rem; }
  .gt-kv { font-size:.82rem; color:var(--gt-muted); line-height:1.7; }
  .stButton > button, .stDownloadButton > button { border-radius:11px; font-weight:650; font-size:.87rem; transition:all .15s ease; }
  .stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
    background: var(--gt-grad); border:0; color:#fff; box-shadow: 0 8px 20px -8px rgba(8,145,178,.65);
  }
  .stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover { filter:brightness(1.07); transform:translateY(-1px); }
  .stButton > button:hover, .stDownloadButton > button:hover { border-color:#7DD3FC; }
  div[data-testid="stDataFrame"] { border:1px solid var(--gt-line); border-radius:14px; overflow:hidden; box-shadow:0 10px 26px -20px rgba(11,18,32,.3); }
  div[data-testid="stExpander"] { border-radius:14px; }
  [data-testid="stChatMessage"] { border-radius:14px; }
  input, textarea { border-radius:10px !important; }
  [data-testid="stAppDeployButton"], .stDeployButton, [data-testid="stDeployButton"] { display:none !important; visibility:hidden !important; }
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
