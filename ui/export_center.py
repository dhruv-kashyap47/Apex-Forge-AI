from __future__ import annotations

import io
import json
import zipfile

import pandas as pd
import streamlit as st

from db import queries
from ui.styles import section_title


def render() -> None:
    st.markdown(
        """
        <div style="margin-bottom:1.5rem">
          <h1 style="font-size:1.8rem;font-weight:800;color:#f1f5f9;margin:0">⬇ Export Center</h1>
          <p style="color:#64748b;margin:0.3rem 0 0">Generate registry, match decisions, review queue, audit logs, and bundle exports.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    registry = pd.DataFrame(queries.execute("SELECT * FROM v_ubid_registry ORDER BY updated_at DESC LIMIT 50000"))
    matches = pd.DataFrame(queries.execute("SELECT * FROM match_edges ORDER BY created_at DESC LIMIT 50000"))
    reviews = pd.DataFrame(queries.execute("SELECT * FROM review_cases ORDER BY opened_at DESC LIMIT 50000"))
    audit = pd.DataFrame(queries.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 50000"))

    st.markdown(section_title("DOWNLOADS"), unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.download_button("Registry CSV", data=registry.to_csv(index=False).encode("utf-8"), file_name="ubid_registry.csv", mime="text/csv")
    with c2:
        st.download_button("Match Decisions JSON", data=matches.to_json(orient="records", indent=2).encode("utf-8"), file_name="match_decisions.json", mime="application/json")
    with c3:
        xlsx = _to_excel({"registry": registry, "matches": matches, "reviews": reviews, "audit": audit})
        st.download_button(
            "Excel Workbook",
            data=xlsx or b"",
            file_name="apexforge_exports.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=xlsx is None,
        )
    with c4:
        bundle = _zip_bundle(registry, matches, reviews, audit)
        st.download_button("ZIP Bundle", data=bundle, file_name="apexforge_exports.zip", mime="application/zip")

    st.markdown(section_title("PREVIEW"), unsafe_allow_html=True)
    tab1, tab2, tab3, tab4 = st.tabs(["Registry", "Matches", "Reviews", "Audit"])
    with tab1:
        st.dataframe(registry.head(200), width="stretch")
    with tab2:
        st.dataframe(matches.head(200), width="stretch")
    with tab3:
        st.dataframe(reviews.head(200), width="stretch")
    with tab4:
        st.dataframe(audit.head(200), width="stretch")


def _to_excel(frames: dict[str, pd.DataFrame]) -> bytes:
    try:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            for sheet, frame in frames.items():
                frame.to_excel(writer, sheet_name=sheet[:31], index=False)
        return buffer.getvalue()
    except Exception:
        st.warning("Excel export is unavailable in this environment.")
        return None


def _zip_bundle(registry: pd.DataFrame, matches: pd.DataFrame, reviews: pd.DataFrame, audit: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("registry.csv", registry.to_csv(index=False))
        zf.writestr("match_decisions.csv", matches.to_csv(index=False))
        zf.writestr("review_queue.csv", reviews.to_csv(index=False))
        zf.writestr("audit_logs.csv", audit.to_csv(index=False))
        zf.writestr("registry.json", registry.to_json(orient="records", indent=2))
    return buffer.getvalue()
