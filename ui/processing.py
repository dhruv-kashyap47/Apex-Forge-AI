from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from db import queries
from engine.resolver import run_resolution
from engine.vitality import classify_all_entities
from ui.styles import section_title, stat_card


def render() -> None:
    st.markdown(
        """
        <div style="margin-bottom:1.5rem">
          <h1 style="font-size:1.8rem;font-weight:800;color:#f1f5f9;margin:0">⚙ Processing Progress</h1>
          <p style="color:#64748b;margin:0.3rem 0 0">Run blocking, matching, clustering, UBID assignment, and status refresh.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    runs = queries.get_latest_processing_runs(10)
    cols = st.columns(4)
    stats = queries.get_dashboard_stats()
    cols[0].markdown(stat_card(stats.get("total_raw_records", 0), "Raw Records"), unsafe_allow_html=True)
    cols[1].markdown(stat_card(stats.get("total_normalized_records", 0), "Normalized"), unsafe_allow_html=True)
    cols[2].markdown(stat_card(stats.get("total_ubids", 0), "UBIDs"), unsafe_allow_html=True)
    cols[3].markdown(stat_card(stats.get("open_review_cases", 0), "Review Cases"), unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Run Matching & UBID Assignment", type="primary"):
            with st.spinner("Running resolution pipeline..."):
                run = queries.create_processing_run("MATCHING", triggered_by="ui")
                result = run_resolution(processing_run_id=run["run_id"])
                queries.finish_processing_run(run["run_id"], "SUCCEEDED", metrics=result)
                _sync_status_events()
                classify_all_entities()
                st.success(f"Processing complete: {result}")
    with c2:
        if st.button("Refresh Status Only"):
            with st.spinner("Refreshing vitality status..."):
                result = classify_all_entities()
                st.success(str(result))

    st.markdown(section_title("LATEST RUNS"), unsafe_allow_html=True)
    if runs:
        for run in runs:
            st.write(
                f"{run.get('created_at')} | {run.get('run_type')} | {run.get('status')} | records={run.get('records_seen', 0)} | pairs={run.get('candidate_edges', 0)}"
            )
    else:
        st.info("No runs yet.")


def _sync_status_events() -> None:
    ubids = queries.get_active_entity_ids(limit=10000)
    inserted = 0
    for entry in ubids:
        ubid = str(entry["ubid"])
        records = queries.get_entity_records(ubid)
        for rec in records:
            event_date = rec.get("activity_date") or rec.get("registration_date") or rec.get("raw_created_at") or datetime.now(timezone.utc)
            event_type = rec.get("status_raw") or "FILING"
            queries.upsert_status_event(
                {
                    "ubid_id": ubid,
                    "raw_record_id": rec.get("raw_record_id"),
                    "event_type": event_type,
                    "event_source": rec.get("department_code"),
                    "event_date": event_date,
                    "activity_weight": 1.0,
                    "derived_status": None,
                    "details": {
                        "business_name": rec.get("business_name"),
                        "source_record_id": str(rec.get("raw_record_id")),
                    },
                }
            )
            inserted += 1
    st.caption(f"Status events materialized: {inserted}")
