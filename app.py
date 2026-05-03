from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from loguru import logger

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", override=False)

from db import queries
from security import collect_findings, fail_if_critical, render_access_gate, render_security_sidebar
from ui.styles import get_css

st.set_page_config(
    page_title="ApexForge AI - UBID Intelligence",
    page_icon="🔗",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(get_css(), unsafe_allow_html=True)

findings = collect_findings()
fail_if_critical(findings)

try:
    queries.bootstrap()
except Exception as exc:
    st.sidebar.error(f"Database bootstrap failed: {exc}")


with st.sidebar:
    st.markdown(
        """
        <div style="padding:0.5rem 0 1.5rem">
          <div class="gv-logo">ApexForge AI</div>
          <div class="gv-tagline">Unified Business Identity Registry</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    page = st.radio(
        "Navigation",
        [
            "Dashboard",
            "Upload & Schema Mapping",
            "Processing Progress",
            "Entity Explorer",
            "Review Queue",
            "UBID Detail",
            "Audit Log Viewer",
            "Export Center",
            "Graph View",
            "Query Builder",
        ],
        label_visibility="collapsed",
    )

    try:
        stats = queries.get_dashboard_stats()
        st.markdown(
            f"""
            <div style="font-size:0.78rem;color:#475569">
              <div style="display:flex;justify-content:space-between;padding:3px 0"><span>UBIDs</span><span style="color:#f59e0b;font-weight:600">{stats.get('total_entities',0):,}</span></div>
              <div style="display:flex;justify-content:space-between;padding:3px 0"><span>Active</span><span style="color:#10b981;font-weight:600">{stats.get('active_count',0):,}</span></div>
              <div style="display:flex;justify-content:space-between;padding:3px 0"><span>Review</span><span style="color:{'#f43f5e' if stats.get('pending_reviews',0) else '#94a3b8'};font-weight:600">{stats.get('pending_reviews',0):,}</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    except Exception:
        st.caption("Database unavailable")

    render_security_sidebar()

if not render_access_gate():
    st.stop()

PAGE_MAP = {
    "Dashboard": ("ui.dashboard", "render"),
    "Upload & Schema Mapping": ("ui.upload", "render"),
    "Processing Progress": ("ui.processing", "render"),
    "Entity Explorer": ("ui.entity_view", "render"),
    "Review Queue": ("ui.review", "render"),
    "UBID Detail": ("ui.ubid_detail", "render"),
    "Audit Log Viewer": ("ui.audit", "render"),
    "Export Center": ("ui.export_center", "render"),
    "Graph View": ("ui.graph", "render"),
    "Query Builder": ("ui.query", "render"),
}

module_name, func_name = PAGE_MAP[page]
try:
    module = __import__(module_name, fromlist=[func_name])
    getattr(module, func_name)()
except Exception as exc:
    logger.exception("Page render error")
    st.error(f"An error occurred: {exc}")
    st.exception(exc)
