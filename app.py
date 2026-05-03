"""
ApexForge AI — Main Streamlit Application
Entry point: streamlit run app.py

Navigation:
  📊 Dashboard      → Command centre + KPIs
  🔍 Entity Explorer → Search + deep-dive
  🧑‍⚖️ Review Panel  → Human-in-the-loop merge/split
  🕸️ Graph View     → UBID cluster visualisation
  🔬 Query Builder  → Structured + SQL queries
  📜 Audit Trail    → Immutable decision log
  ⚙ Admin          → Resolution + vitality controls
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from loguru import logger

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", override=False)
from security import collect_findings, fail_if_critical, render_access_gate, render_security_sidebar

# ── Page config — MUST be first Streamlit call ────────────────────────────────
st.set_page_config(
    page_title="ApexForge AI — Sovereign UBID Intelligence",
    page_icon="🔗",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help":    "https://github.com/apexforge-ai",
        "About":       "ApexForge AI v1.0 — AI for Bharat Hackathon 2026",
    }
)

# ── Inject global styles ──────────────────────────────────────────────────────
from ui.styles import get_css
st.markdown(get_css(), unsafe_allow_html=True)

security_findings = collect_findings()
fail_if_critical(security_findings)

# ── Sidebar navigation ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:0.5rem 0 1.5rem">
      <div class="gv-logo">ApexForge AI</div>
      <div class="gv-tagline">Sovereign · Explainable · Scalable</div>
    </div>
    """, unsafe_allow_html=True)

    page = st.radio(
        "Navigation",
        [
            "📊  Dashboard",
            "🔍  Entity Explorer",
            "🧑‍⚖️  Review Panel",
            "🕸️  Graph View",
            "🔬  Query Builder",
            "📜  Audit Trail",
            "⚙️  Admin / Controls",
        ],
        label_visibility="collapsed",
    )

    st.markdown("---")

    # ── Quick stats in sidebar ────────────────────────────────────────────
    try:
        from db import queries
        stats = queries.get_dashboard_stats()
        if stats:
            total = stats.get("total_entities", 0)
            active = stats.get("active_count", 0)
            pending = stats.get("pending_reviews", 0)
            st.markdown(f"""
            <div style="font-size:0.78rem;color:#475569">
              <div style="display:flex;justify-content:space-between;padding:3px 0">
                <span>Total UBIDs</span>
                <span style="color:#f59e0b;font-weight:600">{total:,}</span>
              </div>
              <div style="display:flex;justify-content:space-between;padding:3px 0">
                <span>Active Businesses</span>
                <span style="color:#10b981;font-weight:600">{active:,}</span>
              </div>
              <div style="display:flex;justify-content:space-between;padding:3px 0">
                <span>Pending Review</span>
                <span style="color:{'#f43f5e' if pending>0 else '#94a3b8'};font-weight:600">{pending:,}</span>
              </div>
            </div>
            """, unsafe_allow_html=True)
    except Exception:
        st.caption("DB not connected")

    st.markdown("---")
    st.markdown("""
    <div style="font-size:0.72rem;color:#334155;text-align:center">
      Version 1.0.0 · AI for Bharat 2026<br>
      Karnataka Commerce & Industry<br>
      Theme 1: UBID + Business Intelligence<br><br>
      <span style="color:#1e3a8a">● All models run locally</span><br>
      <span style="color:#1e3a8a">● No PII to external APIs</span><br>
      <span style="color:#1e3a8a">● Fully sovereign & auditable</span>
    </div>
    """, unsafe_allow_html=True)

    render_security_sidebar()



# ── Admin page (defined before routing so it is available when called) ────────

def _render_admin() -> None:
    from ui.styles import section_title
    from db import queries

    st.markdown("""
    <div style="margin-bottom:1.5rem">
      <h1 style="font-size:1.8rem;font-weight:800;color:#f1f5f9;margin:0">
        ⚙️ Admin / Controls
      </h1>
      <p style="color:#64748b;margin:0.3rem 0 0">
        Trigger resolution, vitality classification, and active learning from the UI
      </p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    with c1:
        st.markdown(section_title("ENTITY RESOLUTION"), unsafe_allow_html=True)
        pin_sel = st.selectbox("Limit to PIN:", ["All PINs", "560001", "560058"],
                                key="admin_pin")
        if st.button("▶ Run Resolution Pipeline", key="admin_resolve", type="primary"):
            with st.spinner("Running entity resolution… (this may take 1-2 minutes on large datasets)"):
                from engine.resolver import run_resolution
                pin = pin_sel if pin_sel != "All PINs" else None
                stats = run_resolution(pin_code=pin)
            st.success(f"Resolution complete! {stats}")
            st.json(stats)

    with c2:
        st.markdown(section_title("VITALITY CLASSIFICATION"), unsafe_allow_html=True)
        if st.button("▶ Classify All Entity Vitality", key="admin_vitality", type="primary"):
            with st.spinner("Classifying vitality… (processing all entities)"):
                from engine.vitality import classify_all_entities
                v_stats = classify_all_entities()
            st.success("Vitality classification complete!")
            st.json(v_stats)

    st.markdown("---")
    st.markdown(section_title("ACTIVE LEARNING — THRESHOLD CALIBRATION"), unsafe_allow_html=True)

    th_stats = queries.get_threshold_stats()
    if th_stats.get("total_merges", 0) > 0 or th_stats.get("total_rejects", 0) > 0:
        st.markdown(f"""
        Based on **{th_stats.get('total_merges',0)} merges** and
        **{th_stats.get('total_rejects',0)} splits** by human reviewers:
        """)
        ac1, ac2 = st.columns(2)
        with ac1:
            avg_merge = float(th_stats.get("avg_merge_confidence") or 0.92)
            suggested_auto = round(avg_merge - 0.03, 2)
            st.metric("Suggested Auto-Link Threshold", f"{suggested_auto*100:.0f}%",
                      delta=f"{(suggested_auto-0.92)*100:.1f}% from default")
        with ac2:
            avg_rej  = float(th_stats.get("avg_reject_confidence") or 0.65)
            min_merge = float(th_stats.get("min_merge_confidence") or 0.65)
            suggested_review = round((avg_rej + min_merge) / 2, 2)
            st.metric("Suggested Review Threshold", f"{suggested_review*100:.0f}%",
                      delta=f"{(suggested_review-0.65)*100:.1f}% from default")

        if st.button("Apply Calibrated Thresholds", key="admin_thresholds"):
            os.environ["THRESHOLD_AUTO_LINK"] = str(suggested_auto)
            os.environ["THRESHOLD_REVIEW"]    = str(suggested_review)
            queries.log_audit("THRESHOLD_UPDATED",
                              f"Thresholds calibrated: auto={suggested_auto}, review={suggested_review}",
                              actor="admin")
            st.success(f"Thresholds updated: auto={suggested_auto}, review={suggested_review}")
    else:
        st.info("Make at least 1 reviewer decision to enable active learning calibration.")

    st.markdown("---")
    st.markdown(section_title("DATABASE HEALTH"), unsafe_allow_html=True)
    from db.connection import health_check
    if health_check():
        st.success("✅ PostgreSQL: Connected and healthy")
    else:
        st.error("❌ PostgreSQL: Connection failed — check .env configuration")

    rec_count = queries.execute_one("SELECT COUNT(*) AS n FROM raw_records") or {}
    ent_count = queries.execute_one("SELECT COUNT(*) AS n FROM entities") or {}
    evt_count = queries.execute_one("SELECT COUNT(*) AS n FROM activity_events") or {}
    col1, col2, col3 = st.columns(3)
    col1.metric("Raw Records",      f"{rec_count.get('n',0):,}")
    col2.metric("Entities (UBIDs)", f"{ent_count.get('n',0):,}")
    col3.metric("Activity Events",  f"{evt_count.get('n',0):,}")


# ── Route to page ─────────────────────────────────────────────────────────────
try:
    from db import queries
    if queries.is_demo_mode():
        with st.sidebar:
            st.caption("Demo datastore active")
    if not render_access_gate():
        st.stop()
    if "Dashboard" in page:
        from ui import dashboard
        dashboard.render()

    elif "Entity Explorer" in page:
        from ui import entity_view
        entity_view.render()

    elif "Review Panel" in page:
        from ui import review
        review.render()

    elif "Graph View" in page:
        from ui import graph
        graph.render()

    elif "Query Builder" in page:
        from ui import query
        query.render()

    elif "Audit Trail" in page:
        from ui import audit
        audit.render()

    elif "Admin" in page:
        _render_admin()

except Exception as exc:
    logger.exception("Page render error")
    st.error(f"⚠ An error occurred: {exc}")
    st.exception(exc)


