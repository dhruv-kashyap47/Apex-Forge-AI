"""
ApexForge AI — Unified Single-File Implementation
Light-mode, minimal, fast. All UI pages merged into one module.
Depends on: streamlit, pandas, plotly, pyvis (optional)
"""

from __future__ import annotations

import io
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from hashlib import sha256
from html import escape as H

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── Optional imports ──────────────────────────────────────────────────────────
try:
    from db import queries
except ImportError:
    queries = None  # type: ignore

try:
    from engine.resolver import run_resolution
    from engine.vitality import compute_vitality, classify_all_entities, survival_trend
    from engine.explainability import explain_vitality
except ImportError:
    run_resolution = classify_all_entities = compute_vitality = survival_trend = explain_vitality = None  # type: ignore

try:
    from ingestion.parser import parse_upload
    from normalization.canonical import normalize_row
    from validation.schema_mapping import CRITICAL_UPLOAD_FIELDS, guess_mapping, validate_required
except ImportError:
    parse_upload = normalize_row = guess_mapping = validate_required = None  # type: ignore
    CRITICAL_UPLOAD_FIELDS = []  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# CSS — Light mode, clean, no heavy effects
# ─────────────────────────────────────────────────────────────────────────────

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=DM+Mono:wght@400;500&display=swap');

:root {
  --bg:       #f8f9fb;
  --surface:  #ffffff;
  --border:   #e2e8f0;
  --text:     #1a202c;
  --muted:    #64748b;
  --accent:   #2563eb;
  --green:    #059669;
  --amber:    #d97706;
  --red:      #dc2626;
  --mono:     'DM Mono', monospace;
}

html, body, [data-testid="stAppViewContainer"] {
  background: var(--bg) !important;
  font-family: 'DM Sans', sans-serif !important;
  color: var(--text) !important;
}

[data-testid="stSidebar"] {
  background: var(--surface) !important;
  border-right: 1px solid var(--border) !important;
}
[data-testid="stHeader"] { background: transparent !important; }

/* Cards */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1rem 1.25rem;
  margin-bottom: 0.75rem;
}

/* Stat tile */
.stat { text-align: center; }
.stat-val { font-size: 1.8rem; font-weight: 700; color: var(--accent); line-height: 1; }
.stat-lbl { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin-top: 4px; }

/* Badges */
.badge {
  display: inline-block; font-size: 0.72rem; font-weight: 600;
  padding: 2px 8px; border-radius: 20px; border: 1px solid currentColor;
}
.badge-active  { color: var(--green);  background: #d1fae5; }
.badge-dormant { color: var(--amber);  background: #fef3c7; }
.badge-closed  { color: var(--red);    background: #fee2e2; }
.badge-unknown { color: var(--muted);  background: #f1f5f9; }

/* UBID mono */
.ubid { font-family: var(--mono); font-size: 0.72rem; color: var(--accent);
        background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 4px; padding: 1px 6px; }

/* Section label */
.sec { font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
       letter-spacing: 0.12em; color: var(--muted); margin-bottom: 0.5rem;
       border-left: 3px solid var(--accent); padding-left: 0.5rem; }

/* Conf bar */
.cbar-out { background: #e2e8f0; border-radius: 20px; height: 6px; overflow: hidden; }
.cbar-in  { height: 6px; border-radius: 20px; }

/* Streamlit overrides */
div[data-testid="metric-container"] {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 0.75rem;
}
.stButton > button {
  border-radius: 8px !important; font-weight: 600 !important;
  transition: opacity 0.15s !important;
}
.stTextInput input, .stSelectbox > div > div, .stMultiSelect > div > div {
  background: var(--surface) !important; border-color: var(--border) !important;
}
hr { border-color: var(--border) !important; }
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _q(fn, *args, **kwargs):
    """Safe query call — returns [] / {} / 0 based on the actual result type."""
    if queries is None:
        return {}
    try:
        result = getattr(queries, fn)(*args, **kwargs)
        return result if result is not None else {}
    except Exception as exc:
        st.error(f"DB error ({fn}): {exc}")
        return {}


def _badge(status: str) -> str:
    cls = f"badge-{(status or 'UNKNOWN').lower()}"
    icons = {"ACTIVE": "●", "DORMANT": "◐", "CLOSED": "○", "UNKNOWN": "?"}
    icon = icons.get(status, "?")
    return f'<span class="badge {cls}">{icon} {H(status)}</span>'


def _ubid(code: str) -> str:
    short = str(code)[:8] + "…"
    return f'<span class="ubid" title="{H(str(code))}">UBID:{short}</span>'


def _sec(text: str) -> str:
    return f'<div class="sec">{H(text)}</div>'


def _stat(value, label: str) -> str:
    return f'<div class="card stat"><div class="stat-val">{value}</div><div class="stat-lbl">{H(label)}</div></div>'


def _conf_bar(score: float) -> str:
    pct = round(score * 100)
    color = "#059669" if score >= 0.92 else "#d97706" if score >= 0.65 else "#dc2626"
    return f'<div class="cbar-out"><div class="cbar-in" style="width:{pct}%;background:{color}"></div></div><small style="color:var(--muted)">{pct}%</small>'


def _chart_layout(**kw) -> dict:
    base = dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans", color="#1a202c"),
        margin=dict(l=0, r=0, t=10, b=0),
    )
    base.update(kw)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# Page: Dashboard
# ─────────────────────────────────────────────────────────────────────────────

def page_dashboard():
    st.markdown("## Command Dashboard")
    st.caption("Live business intelligence across department silos")

    # Debug: Check demo_store instance ID
    try:
        from db.demo_store import demo_store
        print(f"[DASHBOARD DEBUG] demo_store instance ID: {id(demo_store)}")
    except Exception as e:
        print(f"[DASHBOARD DEBUG] Could not get demo_store ID: {e}")

    # Debug: Get actual counts directly from DB
    raw_count = _q("count_raw_records") or 0
    normalized_count = _q("count_normalized_records") or 0
    ubid_count = _q("count_entities") or 0
    print(f"[DASHBOARD DEBUG] Raw: {raw_count}, Normalized: {normalized_count}, UBIDs: {ubid_count}")

    stats = _q("get_dashboard_stats")
    if not isinstance(stats, dict) or not stats:
        st.info("No data loaded. Upload records first.")
        return

    # Ensure stats reflect actual DB counts
    stats["total_raw_records"] = raw_count
    stats["total_normalized_records"] = normalized_count
    stats["total_ubids"] = ubid_count
    stats["total_entities"] = ubid_count

    # Normalise key differences between PG (total_ubids) and demo (total_entities)
    if "total_entities" not in stats:
        stats["total_entities"] = stats.get("total_ubids", 0)

    kpis = [
        (stats.get("total_entities", 0), "Total UBIDs"),
        (stats.get("active_count", 0),   "Active"),
        (stats.get("dormant_count", 0),  "Dormant"),
        (stats.get("closed_count", 0),   "Closed"),
        (stats.get("total_normalized_records", 0), "Normalized"),
        (stats.get("total_raw_records", 0), "Raw Records"),
    ]
    cols = st.columns(6)
    for col, (val, lbl) in zip(cols, kpis):
        col.markdown(_stat(f"{val:,}", lbl), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1.2, 1.2, 1])

    with c1:
        st.markdown(_sec("VITALITY DISTRIBUTION"), unsafe_allow_html=True)
        labels = ["Active", "Dormant", "Closed", "Unknown"]
        values = [stats.get(k, 0) for k in ("active_count","dormant_count","closed_count","unknown_count")]
        colors = ["#059669","#d97706","#dc2626","#94a3b8"]
        fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.55,
                               marker=dict(colors=colors, line=dict(color="#fff", width=2)),
                               textfont=dict(size=12)))
        fig.update_layout(**_chart_layout(height=220, showlegend=True,
                                          legend=dict(font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
                                          annotations=[dict(text=f"<b>{sum(values):,}</b>", x=0.5, y=0.5,
                                                            font_size=16, showarrow=False)]))
        st.plotly_chart(fig, width='stretch')

    with c2:
        st.markdown(_sec("ENTITIES BY SECTOR"), unsafe_allow_html=True)
        rows = _q("get_entities_by_sector", 12)
        if rows:
            df = pd.DataFrame(rows)
            fig = px.bar(df, x="total", y="sector", orientation="h",
                         color_discrete_sequence=["#2563eb"], labels={"total":"","sector":""})
            fig.update_layout(**_chart_layout(height=220,
                              xaxis=dict(gridcolor="#e2e8f0"),
                              yaxis=dict(gridcolor="rgba(0,0,0,0)")))
            st.plotly_chart(fig, width='stretch')

    with c3:
        st.markdown(_sec("VITALITY BY PIN CODE"), unsafe_allow_html=True)
        rows = _q("get_vitality_by_pin")
        if rows:
            df = pd.DataFrame(rows)
            for old, new in [("active_count","active"),("dormant_count","dormant")]:
                if old in df.columns: df.rename(columns={old: new}, inplace=True)
            for c in ("active","dormant"):
                if c not in df.columns: df[c] = 0
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df["pin_code"].astype(str), y=pd.to_numeric(df["active"], errors="coerce").fillna(0),
                                 name="Active", marker_color="#059669"))
            fig.add_trace(go.Bar(x=df["pin_code"].astype(str), y=pd.to_numeric(df["dormant"], errors="coerce").fillna(0),
                                 name="Dormant", marker_color="#d97706"))
            fig.update_layout(barmode="stack", **_chart_layout(height=220,
                              xaxis=dict(gridcolor="#e2e8f0"), yaxis=dict(gridcolor="#e2e8f0"),
                              legend=dict(font=dict(size=10), bgcolor="rgba(0,0,0,0)")))
            st.plotly_chart(fig, width='stretch')

    c4, c5 = st.columns([1.5, 1])
    with c4:
        st.markdown(_sec("RESOLUTION METRICS"), unsafe_allow_html=True)
        ms = _q("get_match_stats")
        r1, r2, r3 = st.columns(3)
        r1.metric("Total Pairs", f"{ms.get('total',0):,}")
        r1.metric("Auto-Linked", f"{ms.get('auto_linked',0):,}")
        r2.metric("In Review",   f"{ms.get('in_review',0):,}")
        r2.metric("Merged",      f"{ms.get('merged',0):,}")
        conf = float(ms.get("avg_conf") or 0)
        r3.metric("Avg Conf", f"{conf*100:.1f}%")
        r3.metric("Multi-Dept", f"{stats.get('multi_dept_entities',0):,}")

    with c5:
        st.markdown(_sec("LIVE AUDIT STREAM"), unsafe_allow_html=True)
        logs = _q("get_audit_trail", limit=8)
        ICONS = {"ENTITY_CREATED":"🔗","VITALITY_UPDATED":"💡","RESOLUTION_RUN":"⚙","REVIEWER_DECISION":"👤"}
        for log in logs:
            icon = ICONS.get(log.get("event_type",""), "📝")
            st.markdown(
                f'{icon} <span style="color:var(--muted);font-size:0.8rem">{str(log.get("created_at",""))[:16]}</span> '
                f'<span style="font-size:0.85rem">{H(str(log.get("action",""))[:60])}</span>',
                unsafe_allow_html=True
            )

    # Active learning
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(_sec("ACTIVE LEARNING — REVIEWER FEEDBACK"), unsafe_allow_html=True)
    labels = _q("get_learning_labels")
    merges  = sum(1 for lbl in labels if lbl.get("reviewer_label") == 1)
    rejects = sum(1 for lbl in labels if lbl.get("reviewer_label") == 0)
    a1, a2, a3 = st.columns(3)
    a1.metric("Reviewer Merges", merges)
    a2.metric("Reviewer Splits", rejects)
    a3.metric("Total Labels", len(labels))
    if len(labels) >= 5:
        df = pd.DataFrame(labels)
        fig = px.histogram(df, x="confidence", color="reviewer_label",
                           color_discrete_map={1:"#059669",0:"#dc2626"}, nbins=20, barmode="overlay")
        fig.update_layout(**_chart_layout(height=150, xaxis=dict(gridcolor="#e2e8f0"), yaxis=dict(gridcolor="#e2e8f0"),
                          legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10))))
        st.plotly_chart(fig, width='stretch')


# ─────────────────────────────────────────────────────────────────────────────
# Page: Entity Explorer
# ─────────────────────────────────────────────────────────────────────────────

def page_entity_explorer():
    st.markdown("## Entity Explorer")
    st.caption("Search by name, PAN, GSTIN, or UBID")

    sc1, sc2, sc3 = st.columns([3, 1.5, 1.5])
    with sc1:
        query = st.text_input("Search", label_visibility="collapsed", placeholder="Business name, PAN, GSTIN…",
                              key="ent_q")
    with sc2:
        pin_f = st.selectbox("PIN", ["ALL","560001","560058"], key="ent_pin", label_visibility="collapsed")
    with sc3:
        vit_f = st.selectbox("Vitality", ["ALL","ACTIVE","DORMANT","CLOSED","UNKNOWN"],
                             key="ent_vit", label_visibility="collapsed")

    entities = _q("search_entities", query or "",
                  pin_f if pin_f != "ALL" else None,
                  vit_f if vit_f != "ALL" else None, limit=50)

    if not entities:
        st.info("No entities found.")
        return
    st.caption(f"{len(entities)} entities found")

    DEPT_COLORS = {"GST":"#2563eb","LABOUR":"#7c3aed","FACTORIES":"#db2777","KSPCB":"#059669"}

    for ent in entities:
        ubid_str = str(ent.get("ubid",""))
        name   = ent.get("canonical_name","—")
        pin    = ent.get("pin_code","—")
        sector = ent.get("sector","—")
        status = ent.get("vitality_status","UNKNOWN")
        pulse  = int(ent.get("pulse_score",0) or 0)
        conf   = float(ent.get("confidence_score",0) or 0)
        records = int(ent.get("linked_records",0) or 0)
        depts  = ent.get("departments",[]) or []

        with st.expander(f"{H(str(name))}  ·  PIN {H(str(pin))}  ·  {H(str(sector))}"):
            tl, tr = st.columns([3,1])
            with tl:
                dept_chips = " ".join(
                    f'<span style="font-size:0.7rem;padding:2px 7px;border-radius:12px;'
                    f'background:#eff6ff;color:#2563eb;border:1px solid #bfdbfe">{H(str(d))}</span>'
                    for d in (depts if isinstance(depts, list) else [])
                )
                st.markdown(
                    f'{_ubid(ubid_str)} &nbsp; {_badge(status)} &nbsp; {dept_chips}'
                    f'<br><br>'
                    f'<b>PAN:</b> <code>{H(str(ent.get("pan","—") or "—"))}</code> &nbsp; '
                    f'<b>GSTIN:</b> <code>{H(str(ent.get("gstin","—") or "—")[:18])}</code> &nbsp; '
                    f'<b>Records:</b> {records} &nbsp; <b>Conf:</b> {conf*100:.1f}%',
                    unsafe_allow_html=True
                )
            with tr:
                pulse_color = "#059669" if pulse >= 65 else "#d97706" if pulse >= 35 else "#dc2626"
                st.markdown(
                    f'<div style="text-align:center;padding-top:0.5rem">'
                    f'<div style="width:64px;height:64px;border-radius:50%;border:3px solid {pulse_color};'
                    f'display:flex;align-items:center;justify-content:center;flex-direction:column;margin:auto">'
                    f'<div style="color:{pulse_color};font-size:1.2rem;font-weight:700">{pulse}</div>'
                    f'<div style="font-size:0.6rem;color:var(--muted)">PULSE</div></div></div>',
                    unsafe_allow_html=True
                )

            tab1, tab2, tab3, tab4 = st.tabs(["Linked Records","Activity Timeline","Vitality","Audit"])

            with tab1:
                recs = _q("get_entity_records", ubid_str)
                if not recs:
                    st.caption("No records linked.")
                else:
                    for rec in recs:
                        dept = rec.get("department_code","")
                        color = DEPT_COLORS.get(dept,"#94a3b8")
                        st.markdown(
                            f'<div class="card" style="border-left:3px solid {color};padding:0.6rem 1rem">'
                            f'<span style="color:{color};font-size:0.72rem;font-weight:700">{H(str(dept))}</span>'
                            f' <span style="font-weight:600">{H(str(rec.get("business_name","")))}</span>'
                            f'<div style="font-size:0.78rem;color:var(--muted)">'
                            f'PAN: {H(str(rec.get("pan","—") or "—"))} | '
                            f'Conf: {float(rec.get("link_confidence",0))*100:.0f}% | '
                            f'By: {H(str(rec.get("linked_by","system")))}</div></div>',
                            unsafe_allow_html=True
                        )

            with tab2:
                events = _q("get_entity_events", ubid_str)
                if events:
                    df = pd.DataFrame(events)
                    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")
                    TYPE_COLORS = {"RENEWAL":"#059669","INSPECTION":"#d97706","FILING":"#2563eb",
                                   "UTILITY":"#7c3aed","COMPLAINT":"#dc2626","SHUTDOWN":"#ef4444"}
                    fig = go.Figure()
                    for etype, color in TYPE_COLORS.items():
                        sub = df[df["event_type"] == etype]
                        if not sub.empty:
                            fig.add_trace(go.Scatter(
                                x=sub["event_date"], y=[etype]*len(sub), mode="markers",
                                marker=dict(size=10, color=color), name=etype,
                                hovertemplate=f"<b>{etype}</b><br>%{{x|%Y-%m-%d}}<extra></extra>"
                            ))
                    fig.update_layout(**_chart_layout(height=180,
                                                      xaxis=dict(gridcolor="#e2e8f0"), yaxis=dict(gridcolor="rgba(0,0,0,0)"),
                                                      legend=dict(orientation="h", yanchor="bottom", y=1, bgcolor="rgba(0,0,0,0)", font=dict(size=10))))
                    st.plotly_chart(fig, width='stretch')

                    if survival_trend:
                        trend = survival_trend(ubid_str)
                        if len(trend) > 2:
                            tdf = pd.DataFrame(trend)
                            fig2 = go.Figure(go.Scatter(
                                x=tdf["date"], y=tdf["survival"], mode="lines+markers",
                                fill="tozeroy", line=dict(color="#d97706", width=2),
                                marker=dict(size=5), fillcolor="rgba(217,119,6,0.08)"
                            ))
                            fig2.update_layout(**_chart_layout(height=110,
                                                               xaxis=dict(gridcolor="#e2e8f0"), yaxis=dict(gridcolor="#e2e8f0", range=[0,1.05]),
                                                               title=dict(text="Vitality Signal Over Time", font=dict(size=11, color="#64748b"))))
                            st.plotly_chart(fig2, width='stretch')
                else:
                    st.caption("No activity events.")

            with tab3:
                if compute_vitality and explain_vitality:
                    try:
                        result = compute_vitality(ubid_str)
                        expl = explain_vitality(result["signals"], result["status"],
                                                result["vitality_score"], result["pulse_score"])
                        st.markdown(
                            f'<div class="card"><b>AI Verdict:</b> {H(str(expl.get("status_desc","")))}'
                            f'<br><span style="font-size:0.82rem;color:var(--muted)">{H(str(expl.get("model_note","")))}</span></div>',
                            unsafe_allow_html=True
                        )
                        for rsn in expl.get("reasons",[]): st.markdown(f"✓ {H(str(rsn))}")
                        for con in expl.get("concerns",[]): st.markdown(f"⚠ {H(str(con))}")
                        bd = result.get("breakdown",{})
                        v1, v2, v3, v4 = st.columns(4)
                        v1.metric("Events", bd.get("event_count",0))
                        v2.metric("Weighted Score", f"{result['vitality_score']*100:.1f}%")
                        v3.metric("Recency Decay", f"{bd.get('decay_factor',0)*100:.1f}%")
                        v4.metric("Event Diversity", f"{bd.get('diversity_bonus',0)*100:.0f}%")
                    except Exception as e:
                        st.warning(f"Vitality analysis unavailable: {e}")
                else:
                    st.caption("Vitality engine not available.")

            with tab4:
                audit_logs = _q("get_audit_trail", entity_ubid=ubid_str, limit=20)
                ICONS = {"ENTITY_CREATED":"🔗","VITALITY_UPDATED":"💡","REVIEWER_DECISION":"👤","RESOLUTION_RUN":"⚙"}
                if not audit_logs:
                    st.caption("No audit events.")
                for log in audit_logs:
                    icon = ICONS.get(log.get("event_type",""),"📝")
                    ts = str(log.get("created_at",""))[:19]
                    st.markdown(
                        f'{icon} <span style="color:var(--muted);font-size:0.8rem">{H(ts)}</span> '
                        f'{H(str(log.get("action","")))} '
                        f'<span style="color:var(--muted)">— {H(str(log.get("actor","system")))}</span>',
                        unsafe_allow_html=True
                    )

            # Override
            st.markdown("---")
            ov1, ov2, ov3 = st.columns([2,1,1])
            with ov1:
                new_status = st.selectbox("Officer Override:", ["— No change —","ACTIVE","DORMANT","CLOSED"],
                                          key=f"ov_{ubid_str}")
            with ov2:
                reason = st.text_input("Reason:", key=f"rsn_{ubid_str}", placeholder="e.g. Site visit confirmed")
            with ov3:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Apply", key=f"apply_{ubid_str}") and new_status != "— No change —":
                    _q("update_entity_vitality", ubid_str, new_status, conf, pulse)
                    _q("log_audit","REVIEWER_DECISION",
                       f"Override: {status} → {new_status}",
                       actor=st.session_state.get("reviewer_identity","system"),
                       entity_ubid=ubid_str,
                       before={"vitality_status": status},
                       after={"vitality_status": new_status},
                       justification=reason)
                    st.success(f"Updated to {new_status}")
                    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Page: Graph Visualiser
# ─────────────────────────────────────────────────────────────────────────────

DEPT_COLORS_G = {"GST":"#2563eb","LABOUR":"#7c3aed","FACTORIES":"#db2777","KSPCB":"#059669","ENTITY":"#d97706"}
EDGE_COLORS_G  = {"AUTO_MERGED":"#059669","APPROVED":"#059669","IN_REVIEW":"#d97706","PENDING":"#d97706","REJECTED":"#dc2626"}


def page_graph():
    st.markdown("## UBID Graph Visualiser")
    st.caption("Entity-resolution graph — nodes = department records, edges = match confidence")

    c1, c2, c3 = st.columns([2,2,1])
    with c1:
        status_filter = st.multiselect("Show edges:", ["AUTO_MERGED","APPROVED","IN_REVIEW","REJECTED"],
                                       default=["AUTO_MERGED","APPROVED","IN_REVIEW"], key="gr_status")
    with c2:
        conf_min = st.slider("Min confidence:", 0.0, 1.0, 0.65, 0.05, key="gr_conf")
    with c3:
        st.markdown("<br>", unsafe_allow_html=True)
        st.button("🔄 Refresh", key="gr_refresh")

    edges = _q("get_all_match_edges", status_filter)
    edges = [e for e in edges if float(e.get("confidence",0)) >= conf_min]

    if not edges:
        st.info("No edges to display. Run entity resolution or lower the confidence threshold.")
        return

    st.caption(f"{len(edges)} edges loaded")

    try:
        from pyvis.network import Network
        net = Network(height="580px", width="100%", bgcolor="#ffffff", font_color="#1a202c", directed=False)
        net.set_options("""{"nodes":{"borderWidth":2,"font":{"size":11}},"edges":{"smooth":{"enabled":true,"type":"dynamic"}},"physics":{"enabled":true,"solver":"forceAtlas2Based","stabilization":{"iterations":150}},"interaction":{"hover":true,"navigationButtons":true,"keyboard":true}}""")

        seen: set[str] = set()
        for edge in edges:
            for nid_k, name_k, dept_k in [("record_a_id","name_a","dept_a"),("record_b_id","name_b","dept_b")]:
                nid = str(edge[nid_k])
                if nid not in seen:
                    dept  = edge.get(dept_k,"GST")
                    color = DEPT_COLORS_G.get(dept,"#94a3b8")
                    label = (edge.get(name_k) or "")[:22]
                    net.add_node(nid, label=label, color=color,
                                 title=f"<b>{edge.get(name_k)}</b><br>Dept: {dept}", size=16)
                    seen.add(nid)
            conf = float(edge.get("confidence",0))
            status = edge.get("match_status","REVIEW")
            net.add_edge(str(edge["record_a_id"]), str(edge["record_b_id"]),
                         value=conf, color=EDGE_COLORS_G.get(status,"#94a3b8"),
                         title=f"Confidence: {conf*100:.1f}%<br>Status: {status}")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w") as f:
            net.save_graph(f.name)
            html_path = f.name
        with open(html_path) as f:
            html_content = f.read()
        os.unlink(html_path)

        import streamlit.components.v1 as components
        components.html(html_content, height=590, scrolling=False)

    except ImportError:
        _graph_plotly_fallback(edges)

    # Legend
    st.markdown("---")
    leg = st.columns(7)
    items = [("●","#2563eb","GST"),("●","#7c3aed","LABOUR"),("●","#db2777","FACTORIES"),
             ("●","#059669","KSPCB"),("—","#059669","Auto-Linked"),("—","#d97706","In Review"),("—","#dc2626","Rejected")]
    for col, (sym, clr, lbl) in zip(leg, items):
        col.markdown(f'<span style="color:{clr}">{sym}</span> <span style="font-size:0.8rem;color:var(--muted)">{lbl}</span>',
                     unsafe_allow_html=True)


def _graph_plotly_fallback(edges):
    import math
    import random
    nodes: dict = {}
    for e in edges:
        for nid_k, name_k, dept_k in [("record_a_id","name_a","dept_a"),("record_b_id","name_b","dept_b")]:
            nid = str(e[nid_k])
            if nid not in nodes:
                a = random.uniform(0, 2*math.pi)
                r = random.uniform(0.1, 1.0)
                nodes[nid] = {"x": r*math.cos(a), "y": r*math.sin(a),
                              "name": e.get(name_k,""), "dept": e.get(dept_k,"")}
    fig = go.Figure()
    for e in edges:
        na, nb = nodes.get(str(e["record_a_id"])), nodes.get(str(e["record_b_id"]))
        if na and nb:
            fig.add_trace(go.Scatter(x=[na["x"],nb["x"],None], y=[na["y"],nb["y"],None],
                                     mode="lines", line=dict(color=EDGE_COLORS_G.get(e.get("match_status",""),"#94a3b8"), width=1),
                                     hoverinfo="none", showlegend=False))
    for dept, color in DEPT_COLORS_G.items():
        if dept == "ENTITY": continue
        dn = {k: v for k,v in nodes.items() if v.get("dept") == dept}
        if dn:
            fig.add_trace(go.Scatter(x=[v["x"] for v in dn.values()], y=[v["y"] for v in dn.values()],
                                     mode="markers+text",
                                     marker=dict(size=12, color=color),
                                     text=[v["name"][:15] for v in dn.values()],
                                     textposition="top center", textfont=dict(size=9),
                                     name=dept))
    fig.update_layout(**_chart_layout(height=520,
                      xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                      yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                      legend=dict(bgcolor="rgba(0,0,0,0)")))
    st.plotly_chart(fig, width='stretch')


# ─────────────────────────────────────────────────────────────────────────────
# Page: Query Builder
# ─────────────────────────────────────────────────────────────────────────────

DEMO_QUERIES = [
    {"label":"🏭 Dormant factories · 560058 · 18m no inspection",
     "params":{"vitality":"DORMANT","pin_code":"560058","sector":"Metal Fabrication","dept":"FACTORIES","no_inspection_months":18,"limit":50}},
    {"label":"⚡ Active GST · Electronics",
     "params":{"vitality":"ACTIVE","pin_code":None,"sector":"Electronics","dept":"GST","no_inspection_months":None,"limit":50}},
    {"label":"🔴 All closed businesses",
     "params":{"vitality":"CLOSED","pin_code":None,"sector":None,"dept":None,"no_inspection_months":None,"limit":100}},
    {"label":"🌿 KSPCB dormant · expired consent",
     "params":{"vitality":"DORMANT","pin_code":None,"sector":None,"dept":"KSPCB","no_inspection_months":12,"limit":50}},
    {"label":"📋 Multi-dept · 560001",
     "params":{"vitality":"ALL","pin_code":"560001","sector":None,"dept":None,"no_inspection_months":None,"limit":100}},
]


def page_query():
    st.markdown("## Query Builder")
    st.caption("Build powerful cross-department queries without SQL")

    st.markdown(_sec("QUICK DEMO QUERIES"), unsafe_allow_html=True)
    dcols = st.columns(len(DEMO_QUERIES))
    for col, dq in zip(dcols, DEMO_QUERIES):
        if col.button(dq["label"], key=f"dq_{dq['label'][:15]}"):
            st.session_state["qb_params"] = dq["params"]

    st.markdown("---")
    preset = st.session_state.get("qb_params", {})

    VITALITY_OPTS = ["ALL","ACTIVE","DORMANT","CLOSED","UNKNOWN"]
    PIN_OPTS = ["(Any)","560001","560058"]
    DEPT_OPTS = ["(Any)","GST","LABOUR","FACTORIES","KSPCB"]

    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        pv = preset.get("vitality","ALL")
        vitality = st.selectbox("Vitality", VITALITY_OPTS, index=VITALITY_OPTS.index(pv) if pv in VITALITY_OPTS else 0, key="qb_vit")
    with fc2:
        pp = preset.get("pin_code","(Any)") or "(Any)"
        pin_code = st.selectbox("PIN Code", PIN_OPTS, index=PIN_OPTS.index(pp) if pp in PIN_OPTS else 0, key="qb_pin")
    with fc3:
        pd_ = preset.get("dept","(Any)") or "(Any)"
        dept = st.selectbox("Department", DEPT_OPTS, index=DEPT_OPTS.index(pd_) if pd_ in DEPT_OPTS else 0, key="qb_dept")

    fc4, fc5, fc6 = st.columns(3)
    with fc4:
        sector = st.text_input("Sector (partial)", value=preset.get("sector","") or "", key="qb_sec")
    with fc5:
        no_insp = st.number_input("No inspection (months)", 0, 60, int(preset.get("no_inspection_months") or 0), key="qb_noinsp")
    with fc6:
        limit = st.slider("Max results", 10, 500, int(preset.get("limit") or 50), key="qb_lim")

    params = {
        "vitality": vitality if vitality != "ALL" else None,
        "pin_code": pin_code if pin_code != "(Any)" else None,
        "dept":     dept if dept != "(Any)" else None,
        "sector":   sector or None,
        "no_inspection_months": no_insp if no_insp > 0 else None,
        "limit":    limit,
    }

    with st.expander("Preview SQL"):
        st.code(_build_sql(params), language="sql")

    if st.button("▶ RUN QUERY", type="primary", key="qb_run"):
        with st.spinner("Executing…"):
            results = _q("run_structured_query", params)
        if not results:
            st.info("No entities match.")
        else:
            df = pd.DataFrame(results)
            st.success(f"✅ {len(results)} entities found")
            c1, c2 = st.columns([2,1])
            with c1:
                disp = [c for c in ["canonical_name","pan","pin_code","sector","vitality_status","pulse_score","record_count"] if c in df.columns]
                ddf = df[disp].copy()
                ddf.columns = ["Business Name","PAN","PIN","Sector","Vitality","Pulse","# Records"][:len(disp)]
                st.dataframe(ddf, width='stretch', height=320)
            with c2:
                if "vitality_status" in df.columns:
                    vc = df["vitality_status"].value_counts().reset_index()
                    vc.columns = ["Status","Count"]
                    fig = px.pie(vc, names="Status", values="Count", hole=0.5,
                                 color="Status", color_discrete_map={"ACTIVE":"#059669","DORMANT":"#d97706","CLOSED":"#dc2626","UNKNOWN":"#94a3b8"})
                    fig.update_layout(**_chart_layout(height=200, showlegend=True,
                                                      legend=dict(font=dict(size=10), bgcolor="rgba(0,0,0,0)")))
                    st.plotly_chart(fig, width='stretch')

            ec1, ec2 = st.columns(2)
            with ec1:
                st.download_button("⬇ CSV", data=df.to_csv(index=False).encode(), file_name="query_results.csv", mime="text/csv")
            with ec2:
                st.download_button("📄 TXT Report", data=_txt_report(results, params).encode(), file_name="query_report.txt", mime="text/plain")

            _q("log_audit","QUERY_EXECUTED", f"Query: {_param_desc(params)} → {len(results)} results", actor="system")


def _build_sql(p: dict) -> str:
    lines = ["SELECT ubid_id, canonical_name, pan, pin_code, sector, vitality_status, pulse_score",
             "FROM   v_ubid_registry WHERE 1=1"]
    if p.get("vitality"):     lines.append(f"  AND  vitality_status = '{p['vitality']}'")
    if p.get("pin_code"):     lines.append(f"  AND  pin_code = '{p['pin_code']}'")
    if p.get("dept"):         lines.append(f"  AND  departments ? '{p['dept']}'")
    if p.get("sector"):       lines.append(f"  AND  sector ILIKE '%{p['sector']}%'")
    if p.get("no_inspection_months"):
        lines.append("  AND  NOT EXISTS (SELECT 1 FROM status_events WHERE ubid_id=v.ubid_id AND event_type='INSPECTION'")
        lines.append(f"         AND event_date > NOW() - INTERVAL '{p['no_inspection_months']} months')")
    lines.append(f"ORDER  BY latest_activity_at ASC NULLS FIRST LIMIT {p.get('limit',50)};")
    return "\n".join(lines)


def _param_desc(p: dict) -> str:
    parts = []
    if p.get("vitality"): parts.append(p["vitality"])
    if p.get("dept"):     parts.append(f"dept={p['dept']}")
    if p.get("sector"):   parts.append(f"sector~{p['sector']}")
    if p.get("pin_code"): parts.append(f"PIN={p['pin_code']}")
    if p.get("no_inspection_months"): parts.append(f"no-insp>{p['no_inspection_months']}m")
    return " & ".join(parts) if parts else "all"


def _txt_report(results, params) -> str:
    lines = ["="*60, "APEXFORGE AI — QUERY REPORT",
             f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}",
             f"Query: {_param_desc(params)}  |  Results: {len(results)}", "="*60, ""]
    for i, r in enumerate(results, 1):
        lines += [f"{i:3}. {r.get('canonical_name','')}",
                  f"     PAN: {r.get('pan','—')}  PIN: {r.get('pin_code','—')}",
                  f"     Vitality: {r.get('vitality_status','—')} (Pulse: {r.get('pulse_score',0)})", ""]
    lines += ["="*60, "All queries are logged to the immutable audit trail.", "="*60]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Page: Review Queue
# ─────────────────────────────────────────────────────────────────────────────

def page_review():
    st.markdown("## Review Queue")
    st.caption("Human-in-the-loop merge / split decisions")

    cols = st.columns(4)
    stats = _q("get_match_stats")
    cols[0].metric("Pending Review", stats.get("in_review", 0))
    cols[1].metric("Auto-Linked",    stats.get("auto_linked", 0))
    cols[2].metric("Approved",       stats.get("merged", 0))
    cols[3].metric("Rejected",       stats.get("rejected", 0))

    cases = _q("get_review_cases", limit=50)
    if not cases:
        st.info("No cases pending review.")
        return

    st.caption(f"{len(cases)} cases")
    for case in cases:
        case_id = str(case.get("case_id",""))
        conf = float(case.get("confidence",0))
        status = str(case.get("match_status","PENDING"))

        with st.expander(f"Case {case_id[:8]}… · Confidence {conf*100:.1f}% · {status}"):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Record A**")
                st.write(f"Name: {case.get('name_a','—')}")
                st.write(f"PAN: {case.get('pan_a','—')}")
                st.write(f"Dept: {case.get('dept_a','—')}")
            with c2:
                st.markdown("**Record B**")
                st.write(f"Name: {case.get('name_b','—')}")
                st.write(f"PAN: {case.get('pan_b','—')}")
                st.write(f"Dept: {case.get('dept_b','—')}")

            st.markdown(_conf_bar(conf), unsafe_allow_html=True)
            st.caption(f"Algorithm: {case.get('match_reason','—')}")

            b1, b2, b3 = st.columns(3)
            if b1.button("✅ Merge", key=f"mrg_{case_id}"):
                _q("approve_match", case_id)
                _q("log_audit","REVIEWER_DECISION", f"Merged case {case_id[:8]}",
                   actor=st.session_state.get("reviewer_identity","system"), confidence=conf)
                st.success("Merged")
                st.rerun()
            if b2.button("❌ Split", key=f"spl_{case_id}"):
                _q("reject_match", case_id)
                _q("log_audit","REVIEWER_DECISION", f"Rejected case {case_id[:8]}",
                   actor=st.session_state.get("reviewer_identity","system"), confidence=conf)
                st.error("Split")
                st.rerun()
            b3.text_input("Note", key=f"note_{case_id}", placeholder="Optional…")


# ─────────────────────────────────────────────────────────────────────────────
# Page: Audit Trail
# ─────────────────────────────────────────────────────────────────────────────

EVT_ICONS  = {"ENTITY_CREATED":"🔗","VITALITY_UPDATED":"💡","RESOLUTION_RUN":"⚙","REVIEWER_DECISION":"👤","QUERY_EXECUTED":"🔬","THRESHOLD_UPDATED":"🎯"}
EVT_COLORS = {"ENTITY_CREATED":"#059669","VITALITY_UPDATED":"#d97706","RESOLUTION_RUN":"#2563eb","REVIEWER_DECISION":"#7c3aed","QUERY_EXECUTED":"#94a3b8"}


def page_audit():
    st.markdown("## Audit Trail")
    st.caption("Immutable log — append-only, full provenance")

    total = _q("count_audit_log") or 0
    st.info(f"**{total:,}** total events — append-only, DPDP Act compliant")

    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        evt_filter = st.multiselect("Event types:", list(EVT_ICONS.keys()), default=list(EVT_ICONS.keys()), key="aud_evt")
    with fc2:
        actor_filter = st.text_input("Actor:", key="aud_actor", placeholder="reviewer1, system…")
    with fc3:
        limit = st.slider("Max entries:", 20, 500, 100, key="aud_lim")

    logs = _q("get_audit_trail", limit=limit)
    if evt_filter:
        logs = [entry for entry in logs if entry.get("event_type") in evt_filter]
    if actor_filter.strip():
        logs = [entry for entry in logs if actor_filter.strip().lower() in (entry.get("actor") or "").lower()]

    if not logs:
        st.info("No events match.")
        return

    view = st.radio("View:", ["Timeline","Table"], horizontal=True, key="aud_view")
    st.caption(f"{len(logs)} events")

    if view == "Timeline":
        for log in logs:
            evt   = log.get("event_type","")
            icon  = EVT_ICONS.get(evt,"📝")
            color = EVT_COLORS.get(evt,"#94a3b8")
            ts    = str(log.get("created_at",""))[:19]
            act   = log.get("action","")
            actor = log.get("actor","system")
            conf  = log.get("confidence")
            ubid  = str(log.get("entity_ubid") or "")[:8]
            just  = log.get("justification","") or ""

            conf_s = f" · {float(conf)*100:.1f}%" if conf else ""
            ubid_s = f" · UBID:{ubid}…" if ubid else ""

            st.markdown(
                f'<div style="display:flex;gap:0.75rem;padding:0.5rem 0;border-bottom:1px solid var(--border);align-items:flex-start">'
                f'<div style="width:26px;height:26px;border-radius:50%;background:{color}22;border:1.5px solid {color};'
                f'display:flex;align-items:center;justify-content:center;font-size:0.85rem;flex-shrink:0">{icon}</div>'
                f'<div><span style="color:{color};font-size:0.7rem;font-weight:700;text-transform:uppercase">{H(evt)}</span>'
                f' <span style="color:var(--muted);font-size:0.78rem">{H(ts)} · {H(str(actor))}{conf_s}{ubid_s}</span>'
                f'<div style="font-size:0.88rem">{H(act)}</div>' +
                (f'<div style="font-size:0.8rem;color:var(--muted);font-style:italic">Note: {H(str(just))}</div>' if just else "") +
                '</div></div>',
                unsafe_allow_html=True
            )
    else:
        df = pd.DataFrame(logs)
        keep = [c for c in ["created_at","event_type","actor","action","confidence","entity_ubid","justification"] if c in df.columns]
        ddf = df[keep].copy()
        if "confidence" in ddf.columns:
            ddf["confidence"] = ddf["confidence"].apply(lambda x: f"{float(x)*100:.1f}%" if x else "—")
        st.dataframe(ddf, width='stretch', height=500)
        st.download_button("⬇ Export CSV", data=df.to_csv(index=False).encode(), file_name="audit_export.csv", mime="text/csv")


# ─────────────────────────────────────────────────────────────────────────────
# Page: Export Center
# ─────────────────────────────────────────────────────────────────────────────

def page_export():
    st.markdown("## Export Center")
    st.caption("Download registry, match decisions, review queue, and audit logs")

    def _load(sql: str) -> pd.DataFrame:
        try:
            if queries:
                return pd.DataFrame(queries.execute(sql))
        except Exception:
            pass
        return pd.DataFrame()

    registry = _load("SELECT * FROM v_ubid_registry ORDER BY updated_at DESC LIMIT 50000")
    matches  = _load("SELECT * FROM match_edges ORDER BY created_at DESC LIMIT 50000")
    reviews  = _load("SELECT * FROM review_cases ORDER BY opened_at DESC LIMIT 50000")
    audit    = _load("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 50000")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.download_button("Registry CSV", data=registry.to_csv(index=False).encode(), file_name="ubid_registry.csv", mime="text/csv")
    with c2:
        st.download_button("Matches JSON", data=matches.to_json(orient="records", indent=2).encode(), file_name="match_decisions.json", mime="application/json")
    with c3:
        try:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as wr:
                for name, df in [("registry",registry),("matches",matches),("reviews",reviews),("audit",audit)]:
                    df.to_excel(wr, sheet_name=name[:31], index=False)
            st.download_button("Excel Workbook", data=buf.getvalue(), file_name="apexforge_exports.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except Exception:
            st.warning("Excel export unavailable (openpyxl missing).")
    with c4:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("registry.csv",   registry.to_csv(index=False))
            zf.writestr("matches.csv",    matches.to_csv(index=False))
            zf.writestr("reviews.csv",    reviews.to_csv(index=False))
            zf.writestr("audit.csv",      audit.to_csv(index=False))
            zf.writestr("registry.json",  registry.to_json(orient="records", indent=2))
        st.download_button("ZIP Bundle", data=buf.getvalue(), file_name="apexforge_exports.zip", mime="application/zip")

    tab1, tab2, tab3, tab4 = st.tabs(["Registry","Matches","Reviews","Audit"])
    with tab1: st.dataframe(registry.head(200), width='stretch')
    with tab2: st.dataframe(matches.head(200),  width='stretch')
    with tab3: st.dataframe(reviews.head(200),  width='stretch')
    with tab4: st.dataframe(audit.head(200),    width='stretch')


# ─────────────────────────────────────────────────────────────────────────────
# Page: Upload & Schema Mapping
# ─────────────────────────────────────────────────────────────────────────────

def page_upload():
    st.markdown("## Upload & Schema Mapping")
    st.caption("Import CSV/JSON, map columns, normalize, and stage records")

    if parse_upload is None:
        st.warning("Ingestion engine not available.")
        return

    uploaded = st.file_uploader("Choose CSV or JSON", type=["csv","json"], key="ul_file")
    if not uploaded:
        st.info("Upload a file to begin.")
        return

    df = parse_upload(uploaded, uploaded.name)
    st.markdown(f"**{len(df):,}** rows detected")

    with st.expander("Preview (first 20 rows)"):
        st.dataframe(df.head(20), width='stretch')

    columns = ["(not mapped)"] + list(df.columns)
    default_map = guess_mapping(list(df.columns)) if guess_mapping else {}

    st.markdown(_sec("METADATA"), unsafe_allow_html=True)
    m1, m2, m3 = st.columns(3)
    with m1:
        dept_code  = st.text_input("Department Code", value=st.session_state.get("ul_dept","GST"))
        dataset    = st.text_input("Dataset Name",     value=uploaded.name)
    with m2:
        uploader   = st.text_input("Uploader",         value=st.session_state.get("ul_user","system"))
        source_key = st.text_input("Source Key",       value=uploaded.name.rsplit(".",1)[0])
    with m3:
        st.caption(f"Format: {'CSV' if uploaded.name.lower().endswith('.csv') else 'JSON'}")
        st.caption(f"Size: {len(uploaded.getvalue()):,} bytes")

    st.markdown(_sec("COLUMN MAPPING"), unsafe_allow_html=True)
    FIELDS = ["business_name","pan","gstin","pin_code","district","state","city",
              "address_full","activity_date","registration_date","source_status","sector"]
    mapping = {}
    mc = st.columns(2)
    for i, field in enumerate(FIELDS):
        with mc[i % 2]:
            cur = default_map.get(field)
            sel = st.selectbox(field, columns, index=columns.index(cur) if cur in columns else 0, key=f"mp_{field}")
            mapping[field] = None if sel == "(not mapped)" else sel

    required_fields = CRITICAL_UPLOAD_FIELDS or ["business_name", "address_full"]
    missing = validate_required(mapping, required_fields) if validate_required else []
    if missing:
        st.warning(f"Required fields not mapped: {', '.join(missing)}")
        st.caption("Critical fields must be mapped before staging can continue.")

    if st.button("Stage Upload", type="primary", disabled=bool(missing)):
        with st.spinner("Staging records…"):
            try:
                run  = _q("create_processing_run","INGESTION", triggered_by="ui", triggered_by_user=uploader)
                raw  = uploaded.getvalue()
                upload_rec = _q("create_upload", {
                    "processing_run_id": run["run_id"], "uploader_id": uploader,
                    "uploader_name": uploader, "department_code": dept_code,
                    "dataset_name": dataset, "original_filename": uploaded.name,
                    "content_type": uploaded.type,
                    "file_format": "CSV" if uploaded.name.lower().endswith(".csv") else "JSON",
                    "file_size_bytes": len(raw), "content_sha256": sha256(raw).hexdigest(),
                    "upload_status": "RECEIVED", "schema_mapping": mapping,
                    "parse_summary": {"rows": len(df), "columns": list(df.columns)},
                    "validation_summary": {}, "source_row_count": len(df),
                    "valid_row_count": 0, "rejected_row_count": 0,
                })
                sf = _q("create_source_file", {
                    "upload_id": upload_rec["upload_id"], "file_index": 1,
                    "source_name": dataset, "source_format": upload_rec.get("file_format","CSV"),
                    "original_filename": uploaded.name, "source_checksum": sha256(raw).hexdigest(),
                    "source_metadata": {"department_code": dept_code, "uploader": uploader},
                    "file_status": "IMPORTED",
                })
                staged = 0
                for idx, (_, row) in enumerate(df.iterrows(), 1):
                    raw_row, _ = normalize_row(row.to_dict(), mapping, dept_code, source_key, idx)
                    raw_row.update({"source_file_id": sf["source_file_id"], "processing_run_id": run["run_id"]})
                    if not raw_row.get("business_name") or not raw_row.get("address_full"):
                        continue
                    _q("insert_raw_record", raw_row)
                    staged += 1

                if staged == 0:
                    _q("update_upload", upload_rec["upload_id"], upload_status="REJECTED",
                       valid_row_count=0, rejected_row_count=len(df))
                    _q("finish_processing_run", run["run_id"], "FAILED", error_message="No valid rows were staged")
                    raise ValueError("No valid rows were staged")
                _q("update_upload", upload_rec["upload_id"], upload_status="VALIDATED",
                   valid_row_count=staged, rejected_row_count=max(len(df) - staged, 0))
                _q("finish_processing_run", run["run_id"], "SUCCEEDED", metrics={"ingested": staged})
                _q("log_audit","UPLOAD_STAGED", f"Staged {staged} records from {uploaded.name}",
                   actor=uploader, entity_ubid=str(upload_rec["upload_id"]), run_id=run["run_id"])
                st.success(f"Staged {staged:,} records. Run ID: {run['run_id']}")
                st.session_state["last_upload_run"] = str(run["run_id"])
            except Exception as e:
                st.error(f"Upload failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Page: Processing
# ─────────────────────────────────────────────────────────────────────────────

def page_processing():
    st.markdown("## Processing Progress")
    st.caption("Run blocking, matching, clustering, UBID assignment, and vitality refresh")

    # Debug: Check demo_store instance ID
    try:
        from db.demo_store import demo_store
        print(f"[PROCESSING DEBUG] demo_store instance ID: {id(demo_store)}")
    except Exception as e:
        print(f"[PROCESSING DEBUG] Could not get demo_store ID: {e}")

    # Debug: Get actual counts directly from DB
    raw_count = _q("count_raw_records") or 0
    normalized_count = _q("count_normalized_records") or 0
    ubid_count = _q("count_entities") or 0
    print(f"[PROCESSING DEBUG] Raw: {raw_count}, Normalized: {normalized_count}, UBIDs: {ubid_count}")

    stats = _q("get_dashboard_stats")
    # Ensure stats reflect actual DB counts
    stats["total_raw_records"] = raw_count
    stats["total_normalized_records"] = normalized_count
    stats["total_ubids"] = ubid_count

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Raw Records",     stats.get("total_raw_records",0))
    c2.metric("Normalized",      stats.get("total_normalized_records",0))
    c3.metric("UBIDs",           stats.get("total_ubids",0))
    c4.metric("Review Cases",    stats.get("open_review_cases",0))

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Normalize, Match & Assign UBIDs", type="primary"):
            if run_resolution is None:
                st.error("Resolution engine not available.")
            else:
                with st.spinner("Running resolution pipeline…"):
                    run = None
                    try:
                        # Step 1: Create processing run
                        run = _q("create_processing_run","PIPELINE", triggered_by="ui")
                        print(f"Created processing run: {run.get('run_id')}")

                        # Step 2: Normalize raw records
                        ubids_before = _q("count_entities") or 0
                        print(f"UBIDs before pipeline: {ubids_before}")

                        norm_result = _q("normalize_all_raw_records", processing_run_id=run["run_id"])
                        normalized_count = int(norm_result.get("normalized_count", 0) if isinstance(norm_result, dict) else 0)
                        raw_count = int(norm_result.get("raw_count", 0) if isinstance(norm_result, dict) else 0)

                        print(f"Pipeline Step 1 - Raw count: {raw_count}")
                        print(f"Pipeline Step 1 - Normalized count: {normalized_count}")

                        # Fail loudly if normalization failed
                        if raw_count > 0 and normalized_count == 0:
                            raise Exception(f"Normalization failed: {raw_count} raw records but 0 normalized records")
                        if normalized_count == 0:
                            raise Exception("No records available for processing")

                        # Step 3: Run matching
                        print(f"Pipeline Step 2 - Running matching on {normalized_count} records")
                        result = run_resolution(processing_run_id=run["run_id"])
                        matching_input = result.get("total_records", 0)
                        print(f"Pipeline Step 2 - Matching input size: {matching_input}")

                        # Fail loudly if matching input is zero
                        if normalized_count > 0 and matching_input == 0:
                            raise Exception(f"Pipeline broken: {normalized_count} normalized records but 0 records for matching")

                        # Step 4: UBID creation (handled within run_resolution)
                        ubids_after = _q("count_entities") or 0
                        ubids_created = ubids_after - ubids_before
                        print(f"Pipeline Step 3 - UBIDs created: {ubids_created}")

                        # Step 5: Status events
                        print(f"Pipeline Step 4 - Syncing status events")
                        _sync_status_events()

                        # Step 6: Entity classification
                        if classify_all_entities:
                            print(f"Pipeline Step 5 - Running entity classification")
                            classify_all_entities()

                        merged = {**(norm_result if isinstance(norm_result, dict) else {}), **result}
                        merged.update({
                            "ubids_created": ubids_created,
                            "pipeline_steps_completed": 6
                        })
                        _q("finish_processing_run", run["run_id"], "SUCCEEDED", metrics=merged)

                        print(f"Pipeline completed successfully: {merged}")
                        st.success(f"Pipeline completed: {normalized_count} normalized → {matching_input} matched → {ubids_created} UBIDs created")
                    except Exception as exc:
                        if isinstance(run, dict) and run.get("run_id"):
                            _q("finish_processing_run", run["run_id"], "FAILED", error_message=str(exc))
                        st.warning(str(exc))
    with b2:
        if st.button("Refresh Status Only"):
            if classify_all_entities is None:
                st.error("Vitality engine not available.")
            else:
                with st.spinner("Refreshing…"):
                    r = classify_all_entities()
                    st.success(str(r))

        if queries and queries.is_demo_mode() and st.button("Reset Demo Store"):
            try:
                _q("reset_demo_store")
                st.success("Demo store reset.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    st.markdown(_sec("LATEST RUNS"), unsafe_allow_html=True)
    runs = _q("get_latest_processing_runs", 10)
    if runs:
        for run in runs:
            st.markdown(
                f'`{str(run.get("created_at",""))[:16]}` &nbsp; **{run.get("run_type","")}** &nbsp; '
                f'{run.get("status","")} &nbsp; records={run.get("records_seen",0)} pairs={run.get("candidate_edges",0)}',
                unsafe_allow_html=True
            )
    else:
        st.info("No runs yet.")


def _sync_status_events():
    if queries is None: return
    try:
        ubids = _q("get_active_entity_ids", limit=10000)
        if not ubids:
            print("No active entities found for status sync")
            st.caption("Status events materialized: 0")
            return

        inserted = 0
        errors = 0
        total_records = 0

        for entry in ubids:
            ubid = str(entry["ubid"])
            try:
                records = _q("get_entity_records", ubid)
                if not records:
                    continue

                for rec in records:
                    total_records += 1
                    try:
                        # Ensure datetime consistency
                        event_date = rec.get("activity_date") or rec.get("registration_date") or datetime.now(timezone.utc)
                        if isinstance(event_date, datetime) and event_date.tzinfo is None:
                            event_date = event_date.replace(tzinfo=timezone.utc)
                        elif not isinstance(event_date, datetime):
                            event_date = datetime.now(timezone.utc)

                        _q("upsert_status_event", {
                            "ubid_id": ubid, "raw_record_id": rec.get("raw_record_id"),
                            "event_type": rec.get("status_raw") or "FILING",
                            "event_source": rec.get("department_code"), "event_date": event_date,
                            "activity_weight": 1.0, "derived_status": None,
                            "details": {"business_name": rec.get("business_name"), "source_record_id": str(rec.get("raw_record_id"))},
                        })
                        inserted += 1
                    except Exception as e:
                        print(f"Error syncing status event for {ubid}, record {rec.get('raw_record_id')}: {e}")
                        errors += 1
                        # Continue processing other records for this UBID

            except Exception as e:
                print(f"Error processing UBID {ubid}: {e}")
                errors += 1
                # Continue processing other UBIDs

        print(f"Status sync completed: {inserted} inserted, {errors} errors, {total_records} total records")
        st.caption(f"Status events materialized: {inserted} (errors: {errors})")

    except Exception as e:
        print(f"Critical error in status sync: {e}")
        st.caption(f"Status sync failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# App entry point
# ─────────────────────────────────────────────────────────────────────────────

PAGES = {
    "Dashboard":       ("📊", page_dashboard),
    "Entity Explorer": ("🔍", page_entity_explorer),
    "Graph":           ("🕸️", page_graph),
    "Query Builder":   ("🔬", page_query),
    "Review Queue":    ("📋", page_review),
    "Audit Trail":     ("📜", page_audit),
    "Export Center":   ("⬇",  page_export),
    "Upload":          ("📤", page_upload),
    "Processing":      ("⚙",  page_processing),
}


def main():
    st.set_page_config(
        page_title="ApexForge AI",
        page_icon="🏛",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CSS, unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("### 🏛 ApexForge AI")
        st.caption("Karnataka Business Registry")
        st.markdown("---")

        selection = st.radio(
            "Navigation",
            list(PAGES.keys()),
            format_func=lambda k: f"{PAGES[k][0]}  {k}",
            key="nav",
            label_visibility="collapsed",
        )

        st.markdown("---")
        reviewer = st.text_input("Reviewer ID", value=st.session_state.get("reviewer_identity","officer1"),
                                 key="rev_id", placeholder="Your ID…")
        st.session_state["reviewer_identity"] = reviewer
        st.caption("v2.0 · Light Mode")

    PAGES[selection][1]()


if __name__ == "__main__":
    main()
