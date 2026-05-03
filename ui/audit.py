"""
ApexForge AI — Audit Trail Viewer
Immutable, full-provenance log of every decision in the system.
Demonstrates compliance, reversibility, and accountability to the jury.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from html import escape as html_escape

from db import queries


EVENT_ICONS = {
    "ENTITY_CREATED":    "🔗",
    "VITALITY_UPDATED":  "💡",
    "RESOLUTION_RUN":    "⚙",
    "REVIEWER_DECISION": "👤",
    "QUERY_EXECUTED":    "🔬",
    "THRESHOLD_UPDATED": "🎯",
}

EVENT_COLORS = {
    "ENTITY_CREATED":    "#10b981",
    "VITALITY_UPDATED":  "#f59e0b",
    "RESOLUTION_RUN":    "#60a5fa",
    "REVIEWER_DECISION": "#a78bfa",
    "QUERY_EXECUTED":    "#94a3b8",
}


def render() -> None:
    st.markdown("""
    <div style="margin-bottom:1.5rem">
      <h1 style="font-size:1.8rem;font-weight:800;color:#f1f5f9;margin:0">
        📜 Audit Trail
      </h1>
      <p style="color:#64748b;margin:0.3rem 0 0">
        Immutable log of every decision — append-only, full provenance, reversible by design
      </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Filters ───────────────────────────────────────────────────────────
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        evt_filter = st.multiselect(
            "Event types:",
            list(EVENT_ICONS.keys()),
            default=list(EVENT_ICONS.keys()),
            key="audit_event_type"
        )
    with fc2:
        actor_filter = st.text_input("Filter by actor:", key="audit_actor",
                                      placeholder="reviewer1, system…")
    with fc3:
        limit = st.slider("Max entries:", 20, 500, 100, key="audit_limit")

    # ── Stats bar ─────────────────────────────────────────────────────────
    total = queries.count_audit_log()
    st.markdown(f"""
    <div class="gv-card" style="padding:0.75rem 1rem;display:flex;
         align-items:center;gap:2rem;margin-bottom:1rem">
      <div>
        <div style="color:#f59e0b;font-size:1.4rem;font-weight:800">{total:,}</div>
        <div style="color:#94a3b8;font-size:0.75rem">Total Audit Events</div>
      </div>
      <div style="color:#1e2e52;font-size:1.5rem">|</div>
      <div style="color:#64748b;font-size:0.85rem;flex:1">
        This log is append-only. No event can be deleted or modified.
        Every automated decision and human override is captured here,
        satisfying government auditability and DPDP Act compliance requirements.
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Load logs ─────────────────────────────────────────────────────────
    logs = queries.get_audit_trail(limit=limit)

    # Apply filters
    if evt_filter:
        logs = [log_item for log_item in logs if log_item.get("event_type") in evt_filter]
    if actor_filter.strip():
        logs = [log_item for log_item in logs if actor_filter.strip().lower() in
                (log_item.get("actor") or "").lower()]

    if not logs:
        st.info("No audit events match the current filters.")
        return

    st.markdown(f"<p style='color:#475569;font-size:0.85rem'>{len(logs)} events</p>",
                unsafe_allow_html=True)

    # ── View toggle ───────────────────────────────────────────────────────
    view_mode = st.radio("View:", ["Timeline", "Table"], horizontal=True, key="audit_view")

    if view_mode == "Timeline":
        _render_timeline(logs)
    else:
        _render_table(logs)


def _render_timeline(logs: list[dict]) -> None:
    for log in logs:
        evt   = log.get("event_type", "")
        icon  = EVENT_ICONS.get(evt, "📝")
        color = EVENT_COLORS.get(evt, "#94a3b8")
        ts    = str(log.get("created_at") or "")[:19]
        act   = log.get("action", "")
        actor = log.get("actor", "system")
        conf  = log.get("confidence")
        ubid  = str(log.get("entity_ubid") or "")[:8]
        just  = log.get("justification") or ""

        conf_str = f" · confidence {float(conf)*100:.1f}%" if conf else ""
        ubid_str = f" · UBID:{ubid}…" if ubid else ""

        st.markdown(f"""
        <div style="display:flex;gap:1rem;padding:0.6rem 0;
                    border-bottom:1px solid #1e2e52;align-items:flex-start">
          <div style="flex-shrink:0;width:28px;height:28px;border-radius:50%;
                      background:{color}22;border:1.5px solid {color};
                      display:flex;align-items:center;justify-content:center;
                      font-size:0.9rem">{icon}</div>
          <div style="flex:1">
            <div style="display:flex;gap:0.75rem;align-items:center;flex-wrap:wrap">
              <span style="color:{color};font-size:0.72rem;font-weight:700;
                           text-transform:uppercase">{html_escape(str(evt))}</span>
              <span style="color:#475569;font-size:0.78rem">{html_escape(str(ts))}</span>
              <span style="color:#64748b;font-size:0.78rem">by {html_escape(str(actor))}</span>
              <span style="color:#334155;font-size:0.78rem">{conf_str}{ubid_str}</span>
            </div>
            <div style="color:#94a3b8;font-size:0.88rem;margin-top:0.2rem">{html_escape(str(act))}</div>
            {f'<div style="color:#64748b;font-size:0.80rem;font-style:italic;margin-top:0.1rem">Note: {html_escape(str(just))}</div>' if just else ''}
          </div>
        </div>
        """, unsafe_allow_html=True)


def _render_table(logs: list[dict]) -> None:
    df = pd.DataFrame(logs)
    keep = ["created_at", "event_type", "actor", "action", "confidence",
            "entity_ubid", "justification"]
    keep = [c for c in keep if c in df.columns]
    df = df[keep].copy()
    df.columns = ["Timestamp", "Event Type", "Actor", "Action",
                  "Confidence", "Entity UBID", "Note"][:len(keep)]

    if "Confidence" in df.columns:
        df["Confidence"] = df["Confidence"].apply(
            lambda x: f"{float(x)*100:.1f}%" if x else "—"
        )
    if "Entity UBID" in df.columns:
        df["Entity UBID"] = df["Entity UBID"].apply(
            lambda x: str(x)[:12] + "…" if x else "—"
        )

    st.dataframe(df, width="stretch", height=500)

    # Export
    csv = pd.DataFrame(logs).to_csv(index=False).encode("utf-8")
    st.download_button("⬇ Export Full Audit Log (CSV)", data=csv,
                       file_name="apexforge_audit_export.csv", mime="text/csv")
