from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="GroundTruth — Cloud Lineage Console",
    layout="wide",
    initial_sidebar_state="expanded",
)

from groundtruth.ui import components as ui  # noqa: E402
from groundtruth.ui import state  # noqa: E402
from groundtruth.ui.pages import (  # noqa: E402
    ai_page,
    dependencies,
    graph,
    home,
    inventory,
    investigate,
    lineage,
    report,
    settings_page,
    timeline,
)

PAGE_RENDERERS = {
    "Home / Overview": home.render,
    "Investigate": investigate.render,
    "Resource inventory": inventory.render,
    "Lineage overview": lineage.render,
    "Evidence graph": graph.render,
    "Timeline": timeline.render,
    "Dependencies & activity": dependencies.render,
    "AI explanation": ai_page.render,
    "Evidence report": report.render,
    "Settings / connections": settings_page.render,
}


def _sidebar() -> None:
    settings = state.settings()
    st.sidebar.markdown(
        '<div style="padding:0.6rem 0.2rem 0.9rem;">'
        '<div style="display:flex;align-items:center;gap:0.55rem;">'
        '<div style="width:34px;height:34px;border-radius:9px;background:#0F766E;display:flex;align-items:center;justify-content:center;'
        'font-weight:800;font-size:0.95rem;color:#FFFFFF;">GT</div>'
        '<div><div style="font-size:1.02rem;font-weight:750;color:#FFFFFF;line-height:1.1;">GroundTruth</div>'
        '<div style="font-size:0.7rem;color:#94A3B8;letter-spacing:0.06em;">CLOUD LINEAGE CONSOLE</div></div></div>'
        '<div style="margin-top:0.65rem;font-size:0.82rem;color:#CBD5E1;line-height:1.45;">Find the owner before you touch the resource.</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    st.sidebar.markdown(ui.mode_pill(settings.mode), unsafe_allow_html=True)
    if settings.mode == "fixture":
        st.sidebar.caption("Northgate Production (mirror) · ap-south-1")
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        '<div style="font-size:0.68rem;font-weight:700;letter-spacing:0.12em;color:#64748B;margin-bottom:0.2rem;">WORKSPACE</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.radio("Workspace", state.PAGES, key="nav", label_visibility="collapsed")
    st.sidebar.markdown("---")
    result = state.current_result()
    if result is not None:
        st.sidebar.markdown(
            '<div style="font-size:0.68rem;font-weight:700;letter-spacing:0.12em;color:#64748B;margin-bottom:0.35rem;">ACTIVE INVESTIGATION</div>',
            unsafe_allow_html=True,
        )
        st.sidebar.markdown(f"**{result.resource.name}**")
        st.sidebar.markdown(ui.status_pill(result.status.value), unsafe_allow_html=True)
        st.sidebar.caption(f"{result.resource.region} · {result.investigation_id}")
        if st.sidebar.button("Clear investigation", width="stretch"):
            state.clear_result()
            st.rerun()
    else:
        st.sidebar.caption("No investigation in progress. Open a scenario from Overview or start an investigation.")
    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Investigations are read-only. Changes happen only in the governed Action Center — planned, confirmed, audit-logged."
    )
    st.sidebar.caption(f"v{settings.version} · Deterministic engine · Muse Spark advisory")


def _flash() -> None:
    flash = state.pop_flash()
    if not flash:
        return
    kind = flash.get("kind")
    message = flash.get("message")
    if kind == "success":
        st.success(message)
    elif kind == "warning":
        st.warning(message)
    elif kind == "error":
        st.error(message)
    else:
        st.info(message)


def main() -> None:
    state.init_state()
    ui.inject_css()
    _sidebar()
    _flash()
    page = st.session_state.get("nav", state.PAGES[0])
    renderer = PAGE_RENDERERS.get(page, home.render)
    renderer()
    st.markdown('<hr class="gt-rule">', unsafe_allow_html=True)
    settings = state.settings()
    st.caption(
        f"{settings.app_name} · {settings.tagline} · Status and confidence are decided by the deterministic engine; "
        "Muse Spark explanations are advisory and cite evidence IDs."
    )


if __name__ == "__main__":
    main()
