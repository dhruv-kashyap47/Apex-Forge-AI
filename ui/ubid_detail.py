from __future__ import annotations

from pathlib import Path
import tempfile

import streamlit as st
import streamlit.components.v1 as components

from db import queries
from engine.explainability import explain_vitality
from engine.vitality import compute_vitality
from ui.styles import section_title, ubid_badge, vitality_badge


def render() -> None:
    st.markdown(
        """
        <div style="margin-bottom:1.5rem">
          <h1 style="font-size:1.8rem;font-weight:800;color:#f1f5f9;margin:0">🔎 UBID Detail</h1>
          <p style="color:#64748b;margin:0.3rem 0 0">Inspect one resolved business identity, its records, status, audit trail, and graph.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    search = st.text_input("Search by UBID, PAN, GSTIN, or name")
    hits = queries.search_entities(search or "", limit=10)
    if not hits:
        st.info("Search for a UBID to inspect.")
        return

    chosen = st.selectbox("Select entity", hits, format_func=lambda r: f"{r.get('canonical_name')} | {r.get('ubid_code')}", key="ubid_choice")
    ubid = str(chosen.get("ubid_id"))
    entity = queries.get_entity(ubid)
    if not entity:
        st.warning("Entity not found.")
        return

    st.markdown(f"{ubid_badge(str(entity.get('ubid_code')))} &nbsp; {vitality_badge(str(entity.get('status') or 'UNKNOWN'))}", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Records", entity.get("linked_records", 0))
    c2.metric("Events", entity.get("total_events", 0))
    c3.metric("Status", entity.get("status", "UNKNOWN"))
    c4.metric("Pulse", entity.get("pulse_score", 0))

    st.markdown(section_title("RECORDS"), unsafe_allow_html=True)
    records = queries.get_entity_records(ubid)
    st.dataframe(records, width="stretch", height=260)

    st.markdown(section_title("VITALITY"), unsafe_allow_html=True)
    vitality = compute_vitality(ubid, queries.get_entity_events(ubid))
    expl = explain_vitality(vitality["signals"], vitality["status"], vitality["vitality_score"], vitality["pulse_score"])
    st.write(expl["status_desc"])
    st.write("Reasons:", expl.get("reasons", []))
    st.write("Concerns:", expl.get("concerns", []))

    st.markdown(section_title("GRAPH"), unsafe_allow_html=True)
    _render_graph(entity, records)

    st.markdown(section_title("AUDIT"), unsafe_allow_html=True)
    audit = queries.get_audit_trail(entity_ubid=ubid, limit=20)
    st.dataframe(audit, width="stretch", height=240)


def _render_graph(entity: dict, records: list[dict]) -> None:
    try:
        from pyvis.network import Network

        net = Network(height="500px", width="100%", bgcolor="#0a0f1e", font_color="#f1f5f9")
        net.set_options(
            """
            {
              "physics": { "enabled": true, "solver": "forceAtlas2Based" },
              "nodes": { "shape": "dot", "size": 18 },
              "edges": { "smooth": { "enabled": true } }
            }
            """
        )
        cluster_id = entity.get("cluster_id")
        edges = queries.execute(
            """
            SELECT
                me.left_normalized_record_id,
                me.right_normalized_record_id,
                me.score,
                left_rec.canonical_name AS left_name,
                right_rec.canonical_name AS right_name
            FROM match_edges me
            JOIN normalized_records left_rec ON left_rec.normalized_record_id = me.left_normalized_record_id
            JOIN normalized_records right_rec ON right_rec.normalized_record_id = me.right_normalized_record_id
            WHERE me.ubid_id::text = %s OR me.cluster_id::text = %s
            """,
            (str(entity.get("ubid_id")), str(cluster_id) if cluster_id else str(entity.get("ubid_id"))),
        )
        seen: set[str] = set()
        for rec in records:
            rid = str(rec.get("normalized_record_id"))
            if rid not in seen:
                net.add_node(rid, label=(rec.get("canonical_name") or "")[:24], title=rec.get("business_name") or "")
                seen.add(rid)
        for edge in edges:
            net.add_edge(str(edge["left_normalized_record_id"]), str(edge["right_normalized_record_id"]), value=float(edge.get("score", 0)) / 100.0, title=f"{edge.get('score')}%")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as f:
            net.save_graph(f.name)
            html = Path(f.name).read_text(encoding="utf-8")
        components.html(html, height=520, scrolling=False)
    except Exception:
        st.info("Graph rendering unavailable.")
