"""
ApexForge AI — Dashboard Page
The command-center view: live stats, vitality breakdown, entity resolution metrics.
"""

from __future__ import annotations

from datetime import datetime
from html import escape as html_escape

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from db import queries
from ui.styles import stat_card, vitality_badge, confidence_bar, section_title


def render() -> None:
    # ── Page header ───────────────────────────────────────────────────────
    st.markdown("""
    <div style="margin-bottom:1.5rem">
      <h1 style="font-size:1.8rem;font-weight:800;color:#f1f5f9;margin:0">
        Command Dashboard
      </h1>
      <p style="color:#64748b;margin:0.3rem 0 0">
        Live business intelligence across Karnataka's 40+ department silo network
      </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Load stats ────────────────────────────────────────────────────────
    stats = queries.get_dashboard_stats()
    if not stats:
        st.warning("No data loaded yet. Run the seed script first.")
        _show_seed_instructions()
        return

    # ── KPI row ───────────────────────────────────────────────────────────
    cols = st.columns(6)
    kpis = [
        (stats.get("total_entities", 0),    "Total UBIDs"),
        (stats.get("active_count",    0),    "Active"),
        (stats.get("dormant_count",   0),    "Dormant"),
        (stats.get("closed_count",    0),    "Closed"),
        (stats.get("pending_reviews", 0),    "Pending Review"),
        (stats.get("total_raw_records",0),   "Raw Records"),
    ]
    for col, (val, label) in zip(cols, kpis):
        col.markdown(stat_card(f"{val:,}", label), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Row 2: Charts ─────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([1.2, 1.2, 1])

    with c1:
        st.markdown(section_title("VITALITY DISTRIBUTION"), unsafe_allow_html=True)
        _vitality_donut(stats)

    with c2:
        st.markdown(section_title("ENTITIES BY SECTOR"), unsafe_allow_html=True)
        _sector_bar()

    with c3:
        st.markdown(section_title("VITALITY BY PIN CODE"), unsafe_allow_html=True)
        _pin_heatmap()

    # ── Row 3: Resolution metrics + Audit stream ──────────────────────────
    c4, c5 = st.columns([1.5, 1])

    with c4:
        st.markdown(section_title("RESOLUTION ENGINE METRICS"), unsafe_allow_html=True)
        _resolution_metrics(stats)

    with c5:
        st.markdown(section_title("LIVE AUDIT STREAM"), unsafe_allow_html=True)
        _audit_stream()

    # ── Row 4: Active learning status ────────────────────────────────────
    _active_learning_panel()


# ─── Sub-renderers ────────────────────────────────────────────────────────────

def _vitality_donut(stats: dict) -> None:
    labels = ["Active", "Dormant", "Closed", "Unknown"]
    values = [
        stats.get("active_count",  0),
        stats.get("dormant_count", 0),
        stats.get("closed_count",  0),
        stats.get("unknown_count", 0),
    ]
    colors = ["#10b981", "#f59e0b", "#f43f5e", "#475569"]
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=0.6,
        marker=dict(colors=colors, line=dict(color="#0a0f1e", width=2)),
        textfont=dict(family="Inter", size=13, color="white"),
    ))
    total = sum(values)
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
        legend=dict(font=dict(color="#94a3b8", size=11), bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=0, r=0, t=0, b=0), height=220,
        annotations=[dict(
            text=f"<b>{total:,}</b><br><span style='font-size:10px'>UBIDs</span>",
            x=0.5, y=0.5, font_size=16, font_color="#f1f5f9", showarrow=False
        )]
    )
    st.plotly_chart(fig, width="stretch")


def _sector_bar() -> None:
    rows = queries.get_entities_by_sector(12)
    if not rows:
        st.info("No sector data yet.")
        return
    df = pd.DataFrame(rows)
    fig = px.bar(
        df, x="total", y="sector", orientation="h",
        color_discrete_sequence=["#f59e0b"],
        labels={"total": "", "sector": ""},
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color="#94a3b8"),
        margin=dict(l=0, r=0, t=0, b=0), height=220,
        xaxis=dict(gridcolor="#1e2e52"),
        yaxis=dict(gridcolor="rgba(0,0,0,0)"),
    )
    st.plotly_chart(fig, width="stretch")


def _pin_heatmap() -> None:
    rows = queries.get_vitality_by_pin()
    if not rows:
        st.info("No PIN data yet.")
        return
    df = pd.DataFrame(rows).copy()
    if "active" not in df.columns and "active_count" in df.columns:
        df = df.rename(columns={"active_count": "active"})
    if "dormant" not in df.columns and "dormant_count" in df.columns:
        df = df.rename(columns={"dormant_count": "dormant"})
    for col in ("active", "dormant"):
        if col not in df.columns:
            df[col] = 0
    df["active"] = pd.to_numeric(df["active"], errors="coerce").fillna(0)
    df["dormant"] = pd.to_numeric(df["dormant"], errors="coerce").fillna(0)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["pin_code"].astype(str),
        y=df["active"],
        name="Active",
        marker_color="#10b981",
    ))
    fig.add_trace(go.Bar(
        x=df["pin_code"].astype(str),
        y=df["dormant"],
        name="Dormant",
        marker_color="#f59e0b",
    ))
    fig.update_layout(
        barmode="stack",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color="#94a3b8"),
        margin=dict(l=0, r=0, t=0, b=0), height=220,
        legend=dict(font=dict(color="#94a3b8", size=10), bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(gridcolor="#1e2e52"),
        yaxis=dict(gridcolor="#1e2e52"),
    )
    st.plotly_chart(fig, width="stretch")


def _resolution_metrics(stats: dict) -> None:
    match_stats = queries.get_match_stats()

    cols = st.columns(3)
    with cols[0]:
        st.metric("Total Pairs Evaluated", f"{match_stats.get('total', 0):,}")
        st.metric("Auto-Linked",           f"{match_stats.get('auto_linked', 0):,}")
    with cols[1]:
        st.metric("In Review Queue",       f"{match_stats.get('in_review', 0):,}")
        st.metric("Human Merged",          f"{match_stats.get('merged', 0):,}")
    with cols[2]:
        conf = match_stats.get("avg_conf", 0) or 0
        st.metric("Avg Confidence",        f"{float(conf)*100:.1f}%")
        multi = stats.get("multi_dept_entities", 0)
        st.metric("Multi-Dept Entities",   f"{multi:,}")

    # Threshold indicators
    st.markdown(section_title("ACTIVE THRESHOLDS"), unsafe_allow_html=True)
    th_stats = queries.get_threshold_stats()
    cc1, cc2 = st.columns(2)
    with cc1:
        avg_merge = th_stats.get("avg_merge_confidence") or 0.92
        st.markdown(f"""
        <div class="gv-card" style="padding:0.8rem">
          <div style="color:#94a3b8;font-size:0.72rem;text-transform:uppercase">Auto-Link Threshold</div>
          <div style="color:#10b981;font-size:1.4rem;font-weight:800">≥ 92%</div>
          <div style="color:#64748b;font-size:0.78rem">Avg merge confidence: {float(avg_merge)*100:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)
    with cc2:
        avg_rej = th_stats.get("avg_reject_confidence") or 0.0
        st.markdown(f"""
        <div class="gv-card" style="padding:0.8rem">
          <div style="color:#94a3b8;font-size:0.72rem;text-transform:uppercase">Review Threshold</div>
          <div style="color:#f59e0b;font-size:1.4rem;font-weight:800">65% – 91%</div>
          <div style="color:#64748b;font-size:0.78rem">Avg reject confidence: {float(avg_rej)*100:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)


def _audit_stream() -> None:
    logs = queries.get_audit_trail(limit=8)
    if not logs:
        st.info("No audit events yet.")
        return
    for log in logs:
        ts  = str(log.get("created_at") or "")[:16]
        evt = log.get("event_type", "")
        act = log.get("action", "")[:60]
        actor = log.get("actor", "system")
        icon = {"ENTITY_CREATED": "🔗", "VITALITY_UPDATED": "💡",
                "RESOLUTION_RUN": "⚙", "REVIEWER_DECISION": "👤"}.get(evt, "📝")
        st.markdown(f"""
        <div style="padding:0.4rem 0;border-bottom:1px solid #1e2e52;font-size:0.82rem">
          <span style="color:#f59e0b">{icon}</span>
          <span style="color:#94a3b8"> {ts} </span>
          <span style="color:#f1f5f9">{html_escape(act)}</span>
          <span style="color:#475569"> — {html_escape(str(actor))}</span>
        </div>
        """, unsafe_allow_html=True)


def _active_learning_panel() -> None:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(section_title("ACTIVE LEARNING LOOP — SOVEREIGN FEEDBACK"), unsafe_allow_html=True)

    labels = queries.get_learning_labels()
    merges  = [l for l in labels if l.get("reviewer_label") == 1]
    rejects = [l for l in labels if l.get("reviewer_label") == 0]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="gv-card" style="text-align:center">
          <div style="color:#10b981;font-size:1.8rem;font-weight:800">{len(merges)}</div>
          <div style="color:#94a3b8;font-size:0.78rem">Reviewer MERGES</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="gv-card" style="text-align:center">
          <div style="color:#f43f5e;font-size:1.8rem;font-weight:800">{len(rejects)}</div>
          <div style="color:#94a3b8;font-size:0.78rem">Reviewer SPLITS</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        total_rv = len(labels)
        st.markdown(f"""
        <div class="gv-card" style="text-align:center">
          <div style="color:#f59e0b;font-size:1.8rem;font-weight:800">{total_rv}</div>
          <div style="color:#94a3b8;font-size:0.78rem">Total Labels Generated</div>
        </div>""", unsafe_allow_html=True)

    if len(labels) >= 5:
        df = pd.DataFrame(labels)
        fig = px.histogram(
            df, x="confidence", color="reviewer_label",
            color_discrete_map={1: "#10b981", 0: "#f43f5e"},
            nbins=20, barmode="overlay",
            labels={"confidence": "Confidence Score", "reviewer_label": "Label"},
            title="",
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter", color="#94a3b8"),
            margin=dict(l=0, r=0, t=0, b=0), height=160,
            legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
            xaxis=dict(gridcolor="#1e2e52"),
            yaxis=dict(gridcolor="#1e2e52"),
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.caption("Make reviewer decisions to populate the active learning chart.")


def _show_seed_instructions() -> None:
    st.markdown("""
    <div class="gv-card">
      <div class="gv-section-title">SYSTEM READY STATE</div>
      <pre style="color:#94a3b8;font-size:0.85rem">
No registry data is loaded yet.

1. Open "Upload & Schema Mapping"
2. Stage a CSV or JSON export
3. Open "Processing Progress" to run matching and UBID assignment

If data exists but the dashboard is blank, verify DATABASE_URL and SSL connectivity.
      </pre>
    </div>
    """, unsafe_allow_html=True)
