from __future__ import annotations

from hashlib import sha256
from typing import Any
import json

import pandas as pd
import streamlit as st

from db import queries
from ingestion.parser import parse_upload
from normalization.canonical import normalize_row
from validation.schema_mapping import guess_mapping, validate_required
from ui.styles import section_title, stat_card


def render() -> None:
    st.markdown(
        """
        <div style="margin-bottom:1.5rem">
          <h1 style="font-size:1.8rem;font-weight:800;color:#f1f5f9;margin:0">📤 Upload & Schema Mapping</h1>
          <p style="color:#64748b;margin:0.3rem 0 0">Import CSV/JSON exports, map columns, validate, normalize, and stage records.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader("Choose CSV or JSON file", type=["csv", "json"], key="upload_file")
    if not uploaded:
        st.info("Upload a file to start staging records.")
        return

    df = parse_upload(uploaded, uploaded.name)
    st.markdown(stat_card(len(df), "Rows detected"), unsafe_allow_html=True)

    with st.expander("Preview"):
        st.dataframe(df.head(20), width="stretch")

    columns = ["(not mapped)"] + list(df.columns)
    default_mapping = guess_mapping(list(df.columns))

    st.markdown(section_title("SCHEMA MAPPING"), unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        department_code = st.text_input("Department Code", value=st.session_state.get("upload_department", "GST"))
        dataset_name = st.text_input("Dataset Name", value=st.session_state.get("upload_dataset", uploaded.name))
    with c2:
        uploader_name = st.text_input("Uploader", value=st.session_state.get("upload_user", "system"))
        file_format = "CSV" if uploaded.name.lower().endswith(".csv") else "JSON"
    with c3:
        source_key = st.text_input("Source Key", value=uploaded.name.rsplit(".", 1)[0])

    mapping = {}
    mapping_cols = st.columns(2)
    field_names = ["business_name", "pan", "gstin", "pin_code", "district", "state", "city", "address_full", "activity_date", "registration_date", "source_status", "sector"]
    for idx, field in enumerate(field_names):
        with mapping_cols[idx % 2]:
            current = default_mapping.get(field)
            selected = st.selectbox(f"{field}", columns, index=columns.index(current) if current in columns else 0, key=f"map_{field}")
            mapping[field] = None if selected == "(not mapped)" else selected

    missing = validate_required(mapping, ["business_name"])
    if missing:
        st.warning(f"Missing required mapping: {', '.join(missing)}")

    if st.button("Stage Upload", type="primary", disabled=bool(missing)):
        with st.spinner("Validating, normalizing, and staging..."):
            run = queries.create_processing_run("INGESTION", triggered_by="ui", triggered_by_user=uploader_name, parameters={"dataset_name": dataset_name, "department_code": department_code})
            content_bytes = uploaded.getvalue()
            upload = queries.create_upload(
                {
                    "processing_run_id": run["run_id"],
                    "uploader_id": uploader_name,
                    "uploader_name": uploader_name,
                    "department_code": department_code,
                    "dataset_name": dataset_name,
                    "original_filename": uploaded.name,
                    "content_type": uploaded.type,
                    "file_format": file_format,
                    "file_size_bytes": len(content_bytes),
                    "content_sha256": sha256(content_bytes).hexdigest(),
                    "upload_status": "RECEIVED",
                    "schema_mapping": mapping,
                    "parse_summary": {"rows": len(df), "columns": list(df.columns)},
                    "validation_summary": {},
                    "source_row_count": len(df),
                    "valid_row_count": 0,
                    "rejected_row_count": 0,
                }
            )
            source_file = queries.create_source_file(
                {
                    "upload_id": upload["upload_id"],
                    "file_index": 1,
                    "source_name": dataset_name,
                    "source_format": file_format,
                    "original_filename": uploaded.name,
                    "source_checksum": sha256(content_bytes).hexdigest(),
                    "source_metadata": {"department_code": department_code, "uploader": uploader_name},
                    "file_status": "IMPORTED",
                }
            )

            for idx, (_, row) in enumerate(df.iterrows(), start=1):
                raw_row, norm_row = normalize_row(row.to_dict(), mapping, department_code, source_key, idx)
                raw_row.update({"source_file_id": source_file["source_file_id"], "processing_run_id": run["run_id"]})
                norm_row.update({"raw_record_id": None, "processing_run_id": run["run_id"]})
                raw_saved = queries.insert_raw_record(raw_row)
                norm_row["raw_record_id"] = raw_saved["raw_record_id"]
                norm_row["record_hash"] = raw_saved["record_hash"]
                queries.insert_normalized_record(norm_row)

            queries.update_upload(
                upload["upload_id"],
                upload_status="VALIDATED",
                valid_row_count=len(df),
                rejected_row_count=0,
            )
            queries.finish_processing_run(run["run_id"], "SUCCEEDED", metrics={"ingested": len(df)})
            queries.log_audit(
                "UPLOAD_STAGED",
                f"Staged {len(df)} records from {uploaded.name}",
                actor=uploader_name,
                entity_type="UPLOAD",
                entity_ubid=str(upload["upload_id"]),
                run_id=run["run_id"],
            )
            st.success(f"Staged {len(df)} records. Run ID: {run['run_id']}")
            st.session_state["last_upload_run"] = str(run["run_id"])
