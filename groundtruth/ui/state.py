from __future__ import annotations

from typing import Any

import streamlit as st

from groundtruth.ai import AIExplainService
from groundtruth.config import Settings
from groundtruth.exports import build_evidence_bundle
from groundtruth.models.lineage import LineageResult
from groundtruth.models.report import EvidenceBundle
from groundtruth.services.orchestrator import InvestigationOrchestrator
from groundtruth.storage import SqliteInvestigationRepository

PAGES = [
    "Home / Overview",
    "Investigate",
    "Resource inventory",
    "Lineage overview",
    "Evidence graph",
    "Timeline",
    "Dependencies & activity",
    "AI explanation",
    "Evidence report",
    "Settings / connections",
]


@st.cache_resource
def _settings() -> Settings:
    return Settings.from_env()


@st.cache_resource
def _orchestrator() -> InvestigationOrchestrator:
    return InvestigationOrchestrator(_settings())


@st.cache_resource
def _repository() -> SqliteInvestigationRepository:
    return SqliteInvestigationRepository(_settings().database_url)


@st.cache_resource
def _ai_service() -> AIExplainService:
    return AIExplainService(_settings())


def settings() -> Settings:
    return _settings()


def orchestrator() -> InvestigationOrchestrator:
    return _orchestrator()


def repository() -> SqliteInvestigationRepository:
    return _repository()


def ai_service() -> AIExplainService:
    return _ai_service()


def init_state() -> None:
    st.session_state.setdefault("nav", PAGES[0])
    st.session_state.setdefault("task", None)
    st.session_state.setdefault("result", None)
    st.session_state.setdefault("bundle", None)
    st.session_state.setdefault("stored_id", None)
    st.session_state.setdefault("flash", None)


def current_result() -> LineageResult | None:
    result = st.session_state.get("result")
    return result if isinstance(result, LineageResult) else None


def current_bundle() -> EvidenceBundle | None:
    bundle = st.session_state.get("bundle")
    return bundle if isinstance(bundle, EvidenceBundle) else None


def adopt_result(result: LineageResult, *, persist: bool = True) -> EvidenceBundle:
    if result.ai_explanation is None:
        result.ai_explanation = ai_service().explain(result)
    st.session_state["result"] = result
    bundle = build_evidence_bundle(result, redact=settings().redact_account_ids)
    st.session_state["bundle"] = bundle
    if persist and st.session_state.get("stored_id") != result.investigation_id:
        repository().save(bundle)
        st.session_state["stored_id"] = result.investigation_id
    return bundle


def clear_result() -> None:
    st.session_state["result"] = None
    st.session_state["bundle"] = None
    st.session_state["stored_id"] = None


def set_flash(kind: str, message: str) -> None:
    st.session_state["flash"] = {"kind": kind, "message": message}


def pop_flash() -> dict[str, Any] | None:
    flash = st.session_state.get("flash")
    st.session_state["flash"] = None
    return flash
