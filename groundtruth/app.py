from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="GroundTruth",
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
        '<div style="padding:0.4rem 0 0.8rem;">'
        '<div style="font-size:0.7rem;letter-spacing:0.18em;color:#8FC9BD;font-weight:800;">GROUNDTRUTH</div>'
        '<div style="font-family:Georgia,serif;font-size:1.55rem;font-weight:700;color:#FFFDF8;line-height:1.1;">'
        "Find the owner<br>before you touch it.</div></div>",
        unsafe_allow_html=True,
    )
    st.sidebar.markdown(ui.mode_pill(settings.mode), unsafe_allow_html=True)
    st.sidebar.markdown("---")
    st.sidebar.radio("Workspace", state.PAGES, key="nav")
    st.sidebar.markdown("---")
    result = state.current_result()
    if result is not None:
        st.sidebar.markdown("**Current investigation**")
        st.sidebar.markdown(ui.status_pill(result.status.value), unsafe_allow_html=True)
        st.sidebar.caption(f"{result.resource.name}\n\n`{result.investigation_id}`")
        if st.sidebar.button("Clear current result", width="stretch"):
            state.clear_result()
            st.rerun()
    else:
        st.sidebar.caption("No investigation loaded. Start with a fixture case on Home.")
    st.sidebar.markdown("---")
    st.sidebar.caption("Read-only investigation. No apply, import, delete, invoke, or mutation tools are exposed.")
    st.sidebar.caption(f"v{settings.version} · Fixture-first · Local SQLite metadata")


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
        f"{settings.app_name} · {settings.tagline} · Deterministic engine owns status and confidence · "
        "Muse Spark explanation is advisory · Fixture data is synthetic."
    )


if __name__ == "__main__":
    main()
