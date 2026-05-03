"""
ApexForge AI — Entity Explorer
Search, browse, and deep-dive into any UBID with full linked records + vitality detail.
"""

from __future__ import annotations

import json
from html import escape as html_escape

import plotly.graph_objects as go
import streamlit as st

from db import queries
from engine.vitality import compute_vitality, survival_trend
from engine.explainability import explain_vitality
from ui.styles import (
    section_title, vitality_badge, confidence_bar,
    ubid_badge, stat_card, timeline_dot_class
)


def render() -> None:
    st.markdown("""
    <div style="margin-bottom:1.5rem">
      <h1 style="font-size:1.8rem;font-weight:800;color:#f1f5f9;margin:0">
        🔍 Entity Explorer
      </h1>
      <p style="color:#64748b;margin:0.3rem 0 0">
        Search any business by name, PAN, GSTIN, or UBID — see its full multi-department profile
      </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Search bar ────────────────────────────────────────────────────────
    sc1, sc2, sc3 = st.columns([3, 1.5, 1.5])
    with sc1:
        query = st.text_input("", placeholder="Business name, PAN, GSTIN, or keyword…",
                               key="entity_search", label_visibility="collapsed")
    with sc2:
        pin_filter = st.selectbox("PIN Code", ["ALL", "560001", "560058"], key="entity_pin",
                                   label_visibility="collapsed")
    with sc3:
        vitality_filter = st.selectbox("Vitality", ["ALL", "ACTIVE", "DORMANT", "CLOSED", "UNKNOWN"],
                                        key="entity_vitality", label_visibility="collapsed")

    pin_val = pin_filter if pin_filter != "ALL" else None
    vit_val = vitality_filter if vitality_filter != "ALL" else None
    entities = queries.search_entities(query or "", pin_val, vit_val, limit=50)

    if not entities:
        st.info("No entities found. Try a broader search or seed the database.")
        return

    st.markdown(f"<p style='color:#475569;font-size:0.85rem'>{len(entities)} entities found</p>",
                unsafe_allow_html=True)

    # ── Entity list ────────────────────────────────────────────────────────
    for ent in entities:
        _render_entity_row(ent)


def _render_entity_row(ent: dict) -> None:
    ubid_str = str(ent.get("ubid", ""))
    name     = ent.get("canonical_name", "—")
    pan      = ent.get("pan", "—") or "—"
    pin      = ent.get("pin_code", "—")
    sector   = ent.get("sector", "—")
    depts    = ent.get("departments", []) or []
    status   = ent.get("vitality_status", "UNKNOWN")
    pulse    = int(ent.get("pulse_score", 0) or 0)
    conf     = float(ent.get("confidence_score", 0) or 0)
    records  = int(ent.get("linked_records", 0) or 0)

    dept_chips = " ".join(
        f'<span style="font-size:0.7rem;padding:2px 8px;border-radius:12px;'
        f'background:#1e3a8a;color:#93c5fd;border:1px solid #3b82f6">{html_escape(str(d))}</span>'
        for d in (depts if isinstance(depts, list) else [])
    )

    pulse_color = "#10b981" if pulse >= 65 else "#f59e0b" if pulse >= 35 else "#f43f5e"

    with st.expander(f"  {html_escape(str(name))}  ·  PIN {html_escape(str(pin))}  ·  {html_escape(str(sector))}"):
        top_l, top_r = st.columns([3, 1])

        with top_l:
            st.markdown(f"""
            <div style="margin-bottom:0.8rem">
              {ubid_badge(html_escape(ubid_str))}
              &nbsp; {vitality_badge(status)}
              &nbsp; {dept_chips}
            </div>
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin-bottom:0.75rem">
              <div><div class="field-label">PAN</div>
                   <div style="font-family:monospace;color:#f1f5f9">{html_escape(str(pan))}</div></div>
              <div><div class="field-label">GSTIN</div>
                   <div style="font-family:monospace;color:#f1f5f9;font-size:0.8rem">
                   {html_escape(str(ent.get('gstin') or '—')[:18])}</div></div>
              <div><div class="field-label">Records Linked</div>
                   <div style="color:#f59e0b;font-weight:700">{records}</div></div>
              <div><div class="field-label">Resolution Conf.</div>
                   <div style="color:#10b981;font-weight:700">{conf*100:.1f}%</div></div>
            </div>
            """, unsafe_allow_html=True)

        with top_r:
            # Pulse score ring
            ring_color = pulse_color
            st.markdown(f"""
            <div style="text-align:center;padding:0.5rem">
              <div style="width:72px;height:72px;border-radius:50%;
                          border:4px solid {ring_color};display:flex;align-items:center;
                          justify-content:center;flex-direction:column;margin:0 auto;
                          box-shadow:0 0 16px {ring_color}40">
                <div style="color:{ring_color};font-size:1.3rem;font-weight:800">{pulse}</div>
                <div style="color:#64748b;font-size:0.6rem">PULSE</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        # ── Tabs inside expander ──────────────────────────────────────────
        tab1, tab2, tab3, tab4 = st.tabs(["📋 Linked Records", "📡 Activity Timeline",
                                           "💡 Vitality Analysis", "🔍 Audit Trail"])

        with tab1:
            _render_linked_records(ubid_str)

        with tab2:
            _render_timeline(ubid_str)

        with tab3:
            _render_vitality_analysis(ubid_str, ent)

        with tab4:
            _render_entity_audit(ubid_str)

        # ── Manual vitality override ──────────────────────────────────────
        st.markdown("---")
        ov1, ov2, ov3 = st.columns([2, 1, 1])
        with ov1:
            new_status = st.selectbox(
                "Officer Override:",
                ["— No change —", "ACTIVE", "DORMANT", "CLOSED"],
                key=f"override_{ubid_str}"
            )
        with ov2:
            reason = st.text_input("Reason:", key=f"reason_{ubid_str}",
                                    placeholder="e.g. Site visit confirmed")
        with ov3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Apply Override", key=f"apply_{ubid_str}"):
                if new_status != "— No change —":
                    queries.update_entity_vitality(ubid_str, new_status,
                                                   conf, pulse)
                    queries.log_audit(
                        "REVIEWER_DECISION",
                        f"Manual override: {html_escape(str(status))} → {html_escape(str(new_status))}",
                        actor=st.session_state.get("reviewer_identity", "system"),
                        entity_ubid=ubid_str,
                        before={"vitality_status": status},
                        after={"vitality_status": new_status},
                        justification=reason,
                    )
                    st.success(f"Status updated to {new_status}")
                    st.rerun()


def _render_linked_records(ubid: str) -> None:
    records = queries.get_entity_records(ubid)
    if not records:
        st.caption("No records linked yet.")
        return

    dept_colors = {"GST": "#60a5fa", "LABOUR": "#a78bfa",
                   "FACTORIES": "#f472b6", "KSPCB": "#34d399"}

    for rec in records:
        dept  = rec.get("department_code", "")
        color = dept_colors.get(dept, "#94a3b8")
        st.markdown(f"""
        <div style="background:#0f1628;border:1px solid #1e2e52;border-left:3px solid {color};
                    border-radius:8px;padding:0.75rem 1rem;margin-bottom:0.5rem">
          <div style="display:flex;justify-content:space-between">
            <div>
              <span style="color:{color};font-size:0.72rem;font-weight:700">{html_escape(str(dept))}</span>
              <span style="color:#f1f5f9;font-size:0.92rem;font-weight:600;margin-left:0.75rem">
                {html_escape(str(rec.get('business_name','')))}</span>
            </div>
            <div>
              <span style="color:#10b981;font-size:0.78rem">
                {float(rec.get('link_confidence',0))*100:.0f}% conf</span>
            </div>
          </div>
          <div style="color:#64748b;font-size:0.78rem;margin-top:0.3rem">
            PAN: {html_escape(str(rec.get('pan','—') or '—'))} &nbsp;|&nbsp;
            GSTIN: {html_escape(str(rec.get('gstin','—') or '—')[:18])} &nbsp;|&nbsp;
            Status: {html_escape(str(rec.get('status_raw','—')))} &nbsp;|&nbsp;
            Linked by: {html_escape(str(rec.get('linked_by','system')))}
          </div>
        </div>
        """, unsafe_allow_html=True)


def _render_timeline(ubid: str) -> None:
    events = queries.get_entity_events(ubid)
    if not events:
        st.caption("No activity events recorded.")
        return

    # Chart
    import pandas as pd
    df = pd.DataFrame(events)
    df["event_date"] = pd.to_datetime(df["event_date"])

    fig = go.Figure()
    type_colors = {"RENEWAL": "#10b981", "INSPECTION": "#f59e0b", "FILING": "#60a5fa",
                   "UTILITY": "#a78bfa", "COMPLAINT": "#f43f5e", "SHUTDOWN": "#ef4444"}

    for etype, color in type_colors.items():
        sub = df[df["event_type"] == etype]
        if sub.empty: continue
        fig.add_trace(go.Scatter(
            x=sub["event_date"], y=[etype] * len(sub),
            mode="markers",
            marker=dict(size=12, color=color, line=dict(width=1, color="#0a0f1e")),
            name=etype,
            hovertemplate=f"<b>{etype}</b><br>%{{x|%Y-%m-%d}}<extra></extra>",
        ))

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color="#94a3b8"),
        margin=dict(l=0, r=0, t=10, b=0), height=200,
        xaxis=dict(gridcolor="#1e2e52", showgrid=True),
        yaxis=dict(gridcolor="rgba(0,0,0,0)"),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10),
                    orientation="h", yanchor="bottom", y=1.02),
        showlegend=True,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Survival trend
    trend = survival_trend(ubid)
    if len(trend) > 2:
        tdf = pd.DataFrame(trend)
        fig2 = go.Figure(go.Scatter(
            x=tdf["date"], y=tdf["survival"],
            mode="lines+markers", fill="tozeroy",
            line=dict(color="#f59e0b", width=2),
            marker=dict(size=6, color="#f59e0b"),
            fillcolor="rgba(245,158,11,0.1)",
        ))
        fig2.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter", color="#94a3b8"),
            margin=dict(l=0, r=0, t=0, b=0), height=120,
            xaxis=dict(gridcolor="#1e2e52"),
            yaxis=dict(gridcolor="#1e2e52", title="Vitality Signal",
                       range=[0, 1.05]),
            title=dict(text="Vitality Signal Over Time (Kaplan-Meier proxy)",
                       font=dict(size=11, color="#64748b")),
        )
        st.plotly_chart(fig2, use_container_width=True)


def _render_vitality_analysis(ubid: str, ent: dict) -> None:
    result = compute_vitality(ubid)
    expl   = explain_vitality(
        result["signals"],
        result["status"],
        result["vitality_score"],
        result["pulse_score"],
    )

    st.markdown(f"""
    <div class="explain-panel">
      <div style="color:#94a3b8;font-size:0.72rem;text-transform:uppercase">AI Verdict</div>
      <div style="color:#f1f5f9;margin:0.4rem 0;font-weight:500">{html_escape(str(expl['status_desc']))}</div>
      <div style="color:#64748b;font-size:0.82rem">{html_escape(str(expl['model_note']))}</div>
    </div>
    """, unsafe_allow_html=True)

    for rsn in expl.get("reasons", []):
        st.markdown(f'<div class="reason-item">{html_escape(str(rsn))}</div>', unsafe_allow_html=True)
    for con in expl.get("concerns", []):
        st.markdown(f'<div class="concern-item">{html_escape(str(con))}</div>', unsafe_allow_html=True)

    # Breakdown metrics
    bd = result.get("breakdown", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Events", bd.get("event_count", 0))
    c2.metric("Weighted Score", f"{result['vitality_score']*100:.1f}%")
    c3.metric("Recency Decay", f"{bd.get('decay_factor',0)*100:.1f}%")
    c4.metric("Event Diversity", f"{bd.get('diversity_bonus',0)*100:.0f}%")


def _render_entity_audit(ubid: str) -> None:
    logs = queries.get_audit_trail(entity_ubid=ubid, limit=20)
    if not logs:
        st.caption("No audit events for this entity.")
        return
    for log in logs:
        ts   = str(log.get("created_at") or "")[:19]
        act  = log.get("action", "")
        actor= log.get("actor", "system")
        evt  = log.get("event_type", "")
        conf = log.get("confidence")
        icon = {"ENTITY_CREATED": "🔗", "VITALITY_UPDATED": "💡",
                "REVIEWER_DECISION": "👤", "RESOLUTION_RUN": "⚙"}.get(evt, "📝")
        conf_str = f" · conf:{conf:.2f}" if conf else ""
        st.markdown(f"""
        <div style="font-size:0.82rem;padding:0.4rem 0;border-bottom:1px solid #1e2e52">
          <span style="color:#f59e0b">{icon}</span>
          <span style="color:#475569"> {html_escape(ts)} </span>
          <span style="color:#f1f5f9">{html_escape(act)}</span>
          <span style="color:#475569"> — {html_escape(actor)}{conf_str}</span>
        </div>
        """, unsafe_allow_html=True)
