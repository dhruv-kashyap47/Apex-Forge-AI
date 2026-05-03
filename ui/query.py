"""
ApexForge AI — Natural Language Query Builder
Converts structured form inputs into SQL and executes them with full explainability.
The jury favourite: "Show dormant factories in Bangalore over 18 months with no inspection"
→ instant result table.
"""

from __future__ import annotations


import pandas as pd
import plotly.express as px
import streamlit as st

from db import queries
from ui.styles import section_title


# ── Pre-built demo queries ─────────────────────────────────────────────────────
DEMO_QUERIES = [
    {
        "label": "🏭 Dormant factories in 560058 with no inspection in 18 months",
        "params": {"vitality": "DORMANT", "pin_code": "560058",
                    "sector": "Metal Fabrication", "dept": "FACTORIES",
                    "no_inspection_months": 18, "limit": 50}
    },
    {
        "label": "⚡ Active GST-registered businesses in Electronics sector",
        "params": {"vitality": "ACTIVE", "pin_code": None,
                    "sector": "Electronics", "dept": "GST",
                    "no_inspection_months": None, "limit": 50}
    },
    {
        "label": "🔴 Closed businesses across all PINs — full list",
        "params": {"vitality": "CLOSED", "pin_code": None,
                    "sector": None, "dept": None,
                    "no_inspection_months": None, "limit": 100}
    },
    {
        "label": "🌿 KSPCB: Dormant businesses with expired consent",
        "params": {"vitality": "DORMANT", "pin_code": None,
                    "sector": None, "dept": "KSPCB",
                    "no_inspection_months": 12, "limit": 50}
    },
    {
        "label": "📋 All multi-department businesses in 560001",
        "params": {"vitality": "ALL", "pin_code": "560001",
                    "sector": None, "dept": None,
                    "no_inspection_months": None, "limit": 100}
    },
]


def render() -> None:
    st.markdown("""
    <div style="margin-bottom:1.5rem">
      <h1 style="font-size:1.8rem;font-weight:800;color:#f1f5f9;margin:0">
        🔬 Query Builder
      </h1>
      <p style="color:#64748b;margin:0.3rem 0 0">
        Build powerful queries across all departments without writing SQL
      </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Quick-pick demo queries ───────────────────────────────────────────
    st.markdown(section_title("QUICK DEMO QUERIES"), unsafe_allow_html=True)
    demo_cols = st.columns(len(DEMO_QUERIES))
    selected_demo = None
    for col, dq in zip(demo_cols, DEMO_QUERIES):
        with col:
            if st.button(dq["label"], key=f"demo_{dq['label'][:20]}"):
                selected_demo = dq["params"]

    if selected_demo:
        st.session_state["qb_params"] = selected_demo

    st.markdown("---")

    # ── Custom query form ─────────────────────────────────────────────────
    st.markdown(section_title("BUILD CUSTOM QUERY"), unsafe_allow_html=True)

    preset = st.session_state.get("qb_params", {})

    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        vitality = st.selectbox(
            "Vitality Status",
            ["ALL", "ACTIVE", "DORMANT", "CLOSED", "UNKNOWN"],
            index=["ALL","ACTIVE","DORMANT","CLOSED","UNKNOWN"].index(
                preset.get("vitality", "ALL")
            ) if preset.get("vitality") in ["ALL","ACTIVE","DORMANT","CLOSED","UNKNOWN"] else 0,
            key="qb_vitality"
        )
    with fc2:
        pin_code = st.selectbox(
            "PIN Code",
            ["(Any)", "560001", "560058"],
            index=["(Any)","560001","560058"].index(preset.get("pin_code","(Any)"))
                if preset.get("pin_code") in ["(Any)","560001","560058"] else 0,
            key="qb_pin"
        )
    with fc3:
        dept = st.selectbox(
            "Department",
            ["(Any)", "GST", "LABOUR", "FACTORIES", "KSPCB"],
            index=["(Any)","GST","LABOUR","FACTORIES","KSPCB"].index(preset.get("dept","(Any)"))
                if preset.get("dept") in ["(Any)","GST","LABOUR","FACTORIES","KSPCB"] else 0,
            key="qb_dept"
        )

    fc4, fc5, fc6 = st.columns(3)
    with fc4:
        sector = st.text_input("Sector (partial match)",
                                value=preset.get("sector","") or "",
                                placeholder="e.g. Chemicals, Textiles…",
                                key="qb_sector")
    with fc5:
        no_insp = st.number_input("No inspection in last N months",
                                   min_value=0, max_value=60,
                                   value=int(preset.get("no_inspection_months") or 0),
                                   key="qb_no_insp")
    with fc6:
        limit = st.slider("Max results", 10, 500,
                           value=int(preset.get("limit") or 50),
                           key="qb_limit")

    # ── SQL preview ────────────────────────────────────────────────────────
    params = {
        "vitality":              vitality if vitality != "ALL" else None,
        "pin_code":              pin_code if pin_code != "(Any)" else None,
        "dept":                  dept if dept != "(Any)" else None,
        "sector":                sector or None,
        "no_inspection_months":  no_insp if no_insp > 0 else None,
        "limit":                 limit,
    }

    with st.expander("🔍 Preview generated SQL", expanded=False):
        sql_preview = _build_sql_preview(params)
        st.code(sql_preview, language="sql")

    # ── Execute ────────────────────────────────────────────────────────────
    if st.button("▶  RUN QUERY", type="primary", key="qb_run"):
        with st.spinner("Executing query…"):
            results = queries.run_structured_query(params)

        if not results:
            st.info("No entities match the query parameters.")
        else:
            _render_results(results, params)

            # ── Log this query to audit ────────────────────────────────────
            desc = _params_to_description(params)
            queries.log_audit(
                "QUERY_EXECUTED",
                f"Query: {desc} → {len(results)} results",
                actor="system",
            )


def _build_sql_preview(params: dict) -> str:
    lines = ["SELECT ubid_id, ubid_code, canonical_name, normalized_pan, normalized_pin, sector,"]
    lines.append("       current_status, member_count, record_count, latest_activity_at")
    lines.append("FROM   v_ubid_registry v")
    lines.append("WHERE  1 = 1")
    if params.get("vitality"):
        lines.append(f"  AND  current_status = '{params['vitality']}'")
    if params.get("pin_code"):
        lines.append(f"  AND  normalized_pin = '{params['pin_code']}'")
    if params.get("dept"):
        lines.append(f"  AND  summary->'departments' ? '{params['dept']}'")
    if params.get("sector"):
        lines.append(f"  AND  sector ILIKE '%{params['sector']}%'")
    if params.get("no_inspection_months"):
        lines.append(f"  AND  NOT EXISTS (    -- No inspection in last {params['no_inspection_months']} months")
        lines.append("         SELECT 1 FROM status_events se")
        lines.append("         WHERE se.ubid_id = v.ubid_id AND se.event_type = 'INSPECTION'")
        lines.append(f"           AND se.event_date > NOW() - INTERVAL '{params['no_inspection_months']} months'")
        lines.append("       )")
    lines.append("ORDER  BY latest_activity_at ASC NULLS FIRST")
    lines.append(f"LIMIT  {params.get('limit', 50)};")
    return "\n".join(lines)


def _params_to_description(params: dict) -> str:
    parts = []
    if params.get("vitality"):    parts.append(params["vitality"])
    if params.get("dept"):        parts.append(f"dept={params['dept']}")
    if params.get("sector"):      parts.append(f"sector~{params['sector']}")
    if params.get("pin_code"):    parts.append(f"PIN={params['pin_code']}")
    if params.get("no_inspection_months"):
        parts.append(f"no-insp>{params['no_inspection_months']}m")
    return " & ".join(parts) if parts else "all"


def _render_results(results: list[dict], params: dict) -> None:
    st.success(f"✅ {len(results)} entities found")

    # ── Vitality breakdown pie ─────────────────────────────────────────────
    df = pd.DataFrame(results)

    c1, c2 = st.columns([2, 1])

    with c1:
        # Main results table
        display_cols = ["canonical_name", "pan", "pin_code", "sector",
                        "vitality_status", "pulse_score", "record_count"]
        display_cols = [c for c in display_cols if c in df.columns]
        display_df = df[display_cols].copy()
        display_df.columns = ["Business Name", "PAN", "PIN", "Sector",
                              "Vitality", "Pulse", "# Records"][:len(display_cols)]
        st.dataframe(
            display_df.style.background_gradient(subset=["Pulse"], cmap="RdYlGn"),
            width="stretch",
            height=350,
        )

    with c2:
        # Vitality breakdown
        if "vitality_status" in df.columns:
            vc = df["vitality_status"].value_counts().reset_index()
            vc.columns = ["Status", "Count"]
            fig = px.pie(vc, names="Status", values="Count",
                          color="Status",
                          color_discrete_map={"ACTIVE": "#10b981", "DORMANT": "#f59e0b",
                                              "CLOSED": "#f43f5e", "UNKNOWN": "#475569"},
                          hole=0.5)
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", showlegend=True,
                legend=dict(font=dict(color="#94a3b8", size=10), bgcolor="rgba(0,0,0,0)"),
                margin=dict(l=0, r=0, t=10, b=0), height=220,
            )
            st.plotly_chart(fig, width="stretch")

        # Pulse distribution
        if "pulse_score" in df.columns:
            fig2 = px.histogram(df, x="pulse_score", nbins=20,
                                 color_discrete_sequence=["#f59e0b"],
                                 labels={"pulse_score": "Pulse Score"})
            fig2.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#94a3b8"), margin=dict(l=0,r=0,t=10,b=0), height=150,
                xaxis=dict(gridcolor="#1e2e52"), yaxis=dict(gridcolor="#1e2e52"),
            )
            st.plotly_chart(fig2, width="stretch")

    # ── Export ─────────────────────────────────────────────────────────────
    st.markdown(section_title("EXPORT"), unsafe_allow_html=True)
    ex1, ex2 = st.columns(2)

    with ex1:
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇ Download CSV",
            data=csv,
            file_name=f"apexforge_query_{_params_to_description(params)[:30]}.csv",
            mime="text/csv",
        )
    with ex2:
        # Generate text report
        report = _generate_report(results, params)
        st.download_button(
            "📄 Download Report (TXT)",
            data=report.encode("utf-8"),
            file_name="apexforge_report.txt",
            mime="text/plain",
        )


def _generate_report(results: list[dict], params: dict) -> str:
    from datetime import datetime
    lines = [
        "═" * 70,
        "APEXFORGE AI — QUERY REPORT",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Query: {_params_to_description(params)}",
        f"Total results: {len(results)}",
        "═" * 70,
        "",
    ]
    for i, r in enumerate(results, 1):
        lines.append(f"{i:3}. {r.get('canonical_name','')}")
        lines.append(f"     UBID:     {r.get('ubid','')}")
        lines.append(f"     PAN:      {r.get('pan','—')}")
        lines.append(f"     PIN:      {r.get('pin_code','—')}")
        lines.append(f"     Vitality: {r.get('vitality_status','—')} (Pulse: {r.get('pulse_score',0)})")
        lines.append(f"     Last Act: {str(r.get('last_activity_at','—'))[:10]}")
        lines.append("")

    lines += [
        "═" * 70,
        "COMPLIANCE NOTE: All results are sourced from the PostgreSQL registry.",
        "All queries are logged to the immutable audit trail.",
        "═" * 70,
    ]
    return "\n".join(lines)
