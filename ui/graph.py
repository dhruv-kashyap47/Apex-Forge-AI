"""
ApexForge AI — UBID Graph Visualiser
Interactive network graph showing entity clusters using PyVis.
Nodes = records coloured by department; Edges = match confidence.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from db import queries
from ui.styles import section_title


DEPT_COLORS = {
    "GST":       "#60a5fa",
    "LABOUR":    "#a78bfa",
    "FACTORIES": "#f472b6",
    "KSPCB":     "#34d399",
    "ENTITY":    "#f59e0b",
}

EDGE_COLORS = {
    "AUTO_MERGED": "#10b981",
    "APPROVED":    "#10b981",
    "IN_REVIEW":   "#f59e0b",
    "PENDING":     "#f59e0b",
    "REJECTED":    "#f43f5e",
}


def render() -> None:
    st.markdown("""
    <div style="margin-bottom:1.5rem">
      <h1 style="font-size:1.8rem;font-weight:800;color:#f1f5f9;margin:0">
        🕸️ UBID Graph Visualiser
      </h1>
      <p style="color:#64748b;margin:0.3rem 0 0">
        Live entity-resolution graph — nodes = department records, edges = match confidence
      </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Controls ──────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        status_filter = st.multiselect(
            "Show edges:", ["AUTO_MERGED", "APPROVED", "IN_REVIEW", "REJECTED"],
            default=["AUTO_MERGED", "APPROVED", "IN_REVIEW"],
            key="graph_status",
        )
    with c2:
        conf_min = st.slider("Min confidence:", 0.0, 1.0, 0.65, 0.05, key="graph_conf")
    with c3:
        st.markdown("<br>", unsafe_allow_html=True)
        refresh = st.button("🔄 Refresh", key="graph_refresh")

    # ── Load edges ────────────────────────────────────────────────────────
    edges = queries.get_all_match_edges(status_filter)
    edges = [e for e in edges if float(e.get("confidence", 0)) >= conf_min]

    if not edges:
        st.info("No graph edges to display. Run entity resolution or lower the confidence threshold.")
        return

    st.markdown(f"<p style='color:#475569;font-size:0.85rem'>{len(edges)} edges loaded</p>",
                unsafe_allow_html=True)

    # ── Build PyVis graph ─────────────────────────────────────────────────
    try:
        from pyvis.network import Network

        net = Network(
            height="600px", width="100%",
            bgcolor="#0a0f1e", font_color="#94a3b8",
            directed=False,
        )
        net.set_options("""
        {
          "nodes": {
            "borderWidth": 2,
            "shadow": { "enabled": true, "size": 10 },
            "font": { "size": 11, "color": "#f1f5f9", "background": "#0f1628" }
          },
          "edges": {
            "smooth": { "enabled": true, "type": "dynamic" },
            "shadow": true
          },
          "physics": {
            "enabled": true,
            "solver": "forceAtlas2Based",
            "stabilization": { "iterations": 150 }
          },
          "interaction": {
            "hover": true,
            "navigationButtons": true,
            "keyboard": true
          }
        }
        """)

        seen_nodes: set[str] = set()

        for edge in edges:
            # Node A
            nid_a = str(edge["record_a_id"])
            if nid_a not in seen_nodes:
                dept  = edge.get("dept_a", "GST")
                color = DEPT_COLORS.get(dept, "#94a3b8")
                label = (edge.get("name_a") or "")[:22]
                net.add_node(nid_a, label=label, color=color,
                             title=f"<b>{edge.get('name_a')}</b><br>Dept: {dept}",
                             size=18)
                seen_nodes.add(nid_a)

            # Node B
            nid_b = str(edge["record_b_id"])
            if nid_b not in seen_nodes:
                dept  = edge.get("dept_b", "GST")
                color = DEPT_COLORS.get(dept, "#94a3b8")
                label = (edge.get("name_b") or "")[:22]
                net.add_node(nid_b, label=label, color=color,
                             title=f"<b>{edge.get('name_b')}</b><br>Dept: {dept}",
                             size=18)
                seen_nodes.add(nid_b)

            # Edge
            conf   = float(edge.get("confidence", 0))
            status = edge.get("match_status", "REVIEW")
            ecolor = EDGE_COLORS.get(status, "#475569")
            net.add_edge(
                nid_a, nid_b,
                value=conf,
                color=ecolor,
                title=f"Confidence: {conf*100:.1f}%<br>Status: {status}",
            )

        # Render to temp HTML
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w") as f:
            net.save_graph(f.name)
            html_path = f.name

        with open(html_path, "r") as f:
            html_content = f.read()
        os.unlink(html_path)

        components.html(html_content, height=620, scrolling=False)

    except ImportError:
        _render_plotly_fallback(edges)
        st.caption("Plotly graph renderer active")

    # ── Legend ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(section_title("LEGEND"), unsafe_allow_html=True)
    leg_cols = st.columns(7)
    items = [
        ("●", "#60a5fa", "GST"), ("●", "#a78bfa", "LABOUR"),
        ("●", "#f472b6", "FACTORIES"), ("●", "#34d399", "KSPCB"),
        ("—", "#10b981", "Auto-Linked"), ("—", "#f59e0b", "In Review"),
        ("—", "#f43f5e", "Rejected"),
    ]
    for col, (sym, clr, lbl) in zip(leg_cols, items):
        col.markdown(f'<span style="color:{clr}">{sym}</span> <span style="color:#94a3b8;font-size:0.8rem">{lbl}</span>',
                     unsafe_allow_html=True)


def _render_plotly_fallback(edges: list[dict]) -> None:
    """Plotly scatter fallback if PyVis unavailable."""
    import plotly.graph_objects as go
    import random, math

    nodes: dict[str, dict] = {}
    for e in edges:
        for side in [("record_a_id", "name_a", "dept_a"), ("record_b_id", "name_b", "dept_b")]:
            nid, name_k, dept_k = side
            nid_val = str(e[nid])
            if nid_val not in nodes:
                angle = random.uniform(0, 2 * math.pi)
                r     = random.uniform(0.1, 1.0)
                nodes[nid_val] = {
                    "x": r * math.cos(angle),
                    "y": r * math.sin(angle),
                    "name": e.get(name_k, ""),
                    "dept": e.get(dept_k, ""),
                }

    fig = go.Figure()

    # Edge traces
    for e in edges:
        nid_a = str(e["record_a_id"])
        nid_b = str(e["record_b_id"])
        if nid_a in nodes and nid_b in nodes:
            na, nb = nodes[nid_a], nodes[nid_b]
            status = e.get("match_status", "REVIEW")
            ecolor = EDGE_COLORS.get(status, "#475569")
            fig.add_trace(go.Scatter(
                x=[na["x"], nb["x"], None], y=[na["y"], nb["y"], None],
                mode="lines", line=dict(color=ecolor, width=1.5),
                hoverinfo="none", showlegend=False,
            ))

    # Node traces by dept
    for dept, color in DEPT_COLORS.items():
        if dept == "ENTITY": continue
        dept_nodes = {k: v for k, v in nodes.items() if v.get("dept") == dept}
        if dept_nodes:
            fig.add_trace(go.Scatter(
                x=[v["x"] for v in dept_nodes.values()],
                y=[v["y"] for v in dept_nodes.values()],
                mode="markers+text",
                marker=dict(size=14, color=color, line=dict(width=1, color="#0a0f1e")),
                text=[v["name"][:15] for v in dept_nodes.values()],
                textposition="top center",
                textfont=dict(size=9, color="#94a3b8"),
                name=dept,
            ))

    fig.update_layout(
        paper_bgcolor="#0a0f1e", plot_bgcolor="#0a0f1e",
        font=dict(family="Inter", color="#94a3b8"),
        height=550, margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    st.plotly_chart(fig, width="stretch")
