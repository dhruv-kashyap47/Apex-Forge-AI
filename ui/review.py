"""
ApexForge AI — Human-in-the-Loop Review Panel
The jury's favourite screen: side-by-side record comparison with AI explanation,
confidence signals, SHAP attribution, and one-click Merge/Split decisions.
"""

from __future__ import annotations

import json
from html import escape as html_escape

import plotly.graph_objects as go
import streamlit as st

from db import queries
from engine.explainability import generate_explanation, compute_shap_values
from ui.styles import section_title, confidence_bar


def render() -> None:
    st.markdown("""
    <div style="margin-bottom:1.5rem">
      <h1 style="font-size:1.8rem;font-weight:800;color:#f1f5f9;margin:0">
        🧑‍⚖️ Human Review Panel
      </h1>
      <p style="color:#64748b;margin:0.3rem 0 0">
        AI suggests · Human decides · System learns — every decision is auditable
      </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Reviewer identity ─────────────────────────────────────────────────
    col_rv, col_stats = st.columns([2, 1])
    with col_rv:
        reviewer = st.selectbox("Reviewing as:", ["reviewer1", "reviewer2", "demo", "admin"],
                                 key="reviewer_identity")
    with col_stats:
        pending = queries.count_pending_reviews()
        st.markdown(f"""
        <div class="gv-card" style="padding:0.8rem;text-align:center">
          <div style="color:#f59e0b;font-size:1.4rem;font-weight:800">{pending}</div>
          <div style="color:#94a3b8;font-size:0.78rem">Items in Queue</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ── Load pending matches ──────────────────────────────────────────────
    matches = queries.get_pending_matches(threshold=0.65, limit=20)

    if not matches:
        st.success("✅ Review queue is empty! All matches resolved.")
        st.balloons()
        return

    # ── Session: which match are we reviewing? ────────────────────────────
    if "review_idx" not in st.session_state:
        st.session_state.review_idx = 0

    idx = st.session_state.review_idx
    if idx >= len(matches):
        idx = 0
        st.session_state.review_idx = 0

    match = matches[idx]

    # ── Progress bar ──────────────────────────────────────────────────────
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:1rem;margin-bottom:1rem">
      <div style="color:#94a3b8;font-size:0.85rem">Review {idx+1} of {len(matches)}</div>
      <div style="flex:1;background:#1e2e52;height:6px;border-radius:4px">
        <div style="width:{((idx+1)/len(matches))*100:.0f}%;height:6px;background:linear-gradient(90deg,#f59e0b,#10b981);border-radius:4px"></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Build explanation ─────────────────────────────────────────────────
    explanation_raw = match.get("explanation") or "{}"
    if isinstance(explanation_raw, str):
        try:
            explanation = json.loads(explanation_raw)
        except Exception:
            explanation = {}
    else:
        explanation = explanation_raw or {}

    if not explanation.get("signals"):
        explanation = generate_explanation(match)

    # ── AI Verdict banner ─────────────────────────────────────────────────
    conf    = float(match.get("confidence", 0))
    verdict = explanation.get("verdict", "AI is reviewing…")
    color   = "#10b981" if conf >= 0.85 else "#f59e0b" if conf >= 0.65 else "#f43f5e"

    st.markdown(f"""
    <div class="explain-panel" style="margin-bottom:1rem;border-left:4px solid {color}">
      <div style="color:#94a3b8;font-size:0.72rem;text-transform:uppercase;margin-bottom:0.4rem">🤖 AI Verdict</div>
      <div style="color:#f1f5f9;font-size:0.95rem;font-weight:500">{html_escape(str(verdict))}</div>
      {confidence_bar(conf)}
    </div>
    """, unsafe_allow_html=True)

    # ── Side-by-side records ──────────────────────────────────────────────
    st.markdown(section_title("RECORD COMPARISON"), unsafe_allow_html=True)
    left, mid_col, right = st.columns([5, 1, 5])

    with left:
        _render_record_card(match, side="a")

    with mid_col:
        st.markdown("""<div style="text-align:center;padding-top:3rem;font-size:1.5rem;color:#475569">⟺</div>""",
                    unsafe_allow_html=True)

    with right:
        _render_record_card(match, side="b")

    # ── Signal breakdown + SHAP ───────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    sig_col, shap_col = st.columns([1, 1])

    with sig_col:
        st.markdown(section_title("SIGNAL BREAKDOWN"), unsafe_allow_html=True)
        _render_signals(explanation)

    with shap_col:
        st.markdown(section_title("SHAP FEATURE ATTRIBUTION"), unsafe_allow_html=True)
        shap_vals = compute_shap_values(match)
        _render_shap_chart(shap_vals)

    # ── AI Reasons & Concerns ─────────────────────────────────────────────
    r_col, c_col = st.columns(2)
    with r_col:
        st.markdown(section_title("REASONS TO MERGE"), unsafe_allow_html=True)
        reasons = explanation.get("reasons", [])
        if reasons:
            for r in reasons:
                st.markdown(f'<div class="reason-item">✓ {html_escape(str(r))}</div>', unsafe_allow_html=True)
        else:
            st.caption("No strong merge reasons found.")

    with c_col:
        st.markdown(section_title("REASONS TO SPLIT"), unsafe_allow_html=True)
        concerns = explanation.get("concerns", [])
        if concerns:
            for c in concerns:
                st.markdown(f'<div class="concern-item">{html_escape(str(c))}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:#10b981;font-size:0.88rem">No concerns raised.</div>',
                        unsafe_allow_html=True)

    # ── Decision panel ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(section_title("MAKE YOUR DECISION"), unsafe_allow_html=True)

    note = st.text_input("Optional note (stored in audit trail):", key=f"note_{idx}",
                          placeholder="e.g. Confirmed same legal entity by CIN check")

    btn1, btn2, btn3, btn4 = st.columns([1.5, 1.5, 1.5, 3])

    with btn1:
        if st.button("✅ MERGE (Same Entity)", key=f"merge_{idx}", type="primary"):
            _submit_decision(match["id"], "MERGED", reviewer, note or "Manually confirmed",
                              match_obj=match)
            st.session_state.review_idx = min(idx + 1, len(matches) - 1)
            st.success("Merged! Graph updated.")
            st.rerun()

    with btn2:
        if st.button("✂️ SPLIT (Different)", key=f"split_{idx}"):
            _submit_decision(match["id"], "SPLIT", reviewer, note or "Manually rejected",
                              match_obj=match)
            st.session_state.review_idx = min(idx + 1, len(matches) - 1)
            st.warning("Split recorded.")
            st.rerun()

    with btn3:
        if st.button("⏭ Skip", key=f"skip_{idx}"):
            st.session_state.review_idx = min(idx + 1, len(matches) - 1)
            st.rerun()

    with btn4:
        nav = st.slider("Jump to:", 1, max(len(matches), 1), idx + 1, key="nav_slider")
        if nav - 1 != idx:
            st.session_state.review_idx = nav - 1
            st.rerun()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _render_record_card(match: dict, side: str) -> None:
    """Render one record card in the side-by-side view."""
    name    = match.get(f"name_{side}", "—")
    dept    = match.get(f"dept_{side}", "—")
    pan     = match.get(f"pan_{side}", "—") or "—"
    gstin   = match.get(f"gstin_{side}", "—") or "—"
    pin     = match.get(f"pin_{side}", "—")
    addr    = match.get(f"address_{side}", "—") or "—"
    sector  = match.get(f"sector_{side}", "—") or "—"
    status  = match.get(f"status_{side}", "—") or "—"

    # Highlight differences between the two sides
    other_side = "b" if side == "a" else "a"
    pan_other  = match.get(f"pan_{other_side}", "")   or ""
    pin_other  = match.get(f"pin_{other_side}", "")   or ""

    pan_class  = "field-value highlight" if pan == pan_other and pan != "—" else \
                 ("field-value field-diff" if pan_other and pan != pan_other else "field-value")
    pin_class  = "field-value highlight" if pin == pin_other else "field-value field-diff"

    dept_colors = {"GST": "#60a5fa", "LABOUR": "#a78bfa",
                   "FACTORIES": "#f472b6", "KSPCB": "#34d399"}
    badge_color = dept_colors.get(dept, "#94a3b8")

    st.markdown(f"""
    <div class="record-card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem">
        <div style="color:{badge_color};font-size:0.72rem;font-weight:700;
                    text-transform:uppercase;letter-spacing:0.1em;
                    background:rgba(255,255,255,0.05);padding:3px 10px;
                    border-radius:20px;border:1px solid {badge_color}">
          {html_escape(str(dept))}
        </div>
        <div style="color:#475569;font-size:0.72rem">Record {side.upper()}</div>
      </div>
      <div class="record-field">
        <div class="field-label">Business Name</div>
        <div class="field-value" style="font-size:1rem;font-weight:700">{html_escape(str(name))}</div>
      </div>
      <div class="record-field">
        <div class="field-label">PAN</div>
        <div class="{pan_class}">{html_escape(str(pan))}</div>
      </div>
      <div class="record-field">
        <div class="field-label">GSTIN</div>
        <div class="field-value">{html_escape(gstin[:20] if gstin != '—' else '—')}</div>
      </div>
      <div class="record-field">
        <div class="field-label">PIN Code</div>
        <div class="{pin_class}">{html_escape(str(pin))}</div>
      </div>
      <div class="record-field">
        <div class="field-label">Sector</div>
        <div class="field-value">{html_escape(str(sector))}</div>
      </div>
      <div class="record-field">
        <div class="field-label">Address</div>
        <div class="field-value" style="font-size:0.82rem;color:#94a3b8">{html_escape(str(addr[:80]))}</div>
      </div>
      <div class="record-field">
        <div class="field-label">Status (Source)</div>
        <div class="field-value">{html_escape(str(status))}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def _render_signals(explanation: dict) -> None:
    signals = explanation.get("signals", [])
    if not signals:
        st.caption("No signals computed.")
        return
    for sig in signals:
        val   = float(sig.get("value", 0))
        label = sig.get("label", sig.get("signal", ""))
        strength = sig.get("strength", "")
        pct = round(val * 100)
        color = "#10b981" if strength in ("definitive","very high") else \
                "#f59e0b" if strength == "high" else \
                "#60a5fa" if strength == "moderate" else "#475569"
        st.markdown(f"""
        <div style="margin-bottom:0.6rem">
          <div style="display:flex;justify-content:space-between;margin-bottom:3px">
            <span style="color:#f1f5f9;font-size:0.84rem">{label}</span>
            <span style="color:{color};font-size:0.84rem;font-weight:600">{pct}%</span>
          </div>
          <div style="background:#1e2e52;border-radius:4px;height:6px">
            <div style="width:{pct}%;height:6px;border-radius:4px;background:{color}"></div>
          </div>
        </div>
        """, unsafe_allow_html=True)


def _render_shap_chart(shap_vals: list[dict]) -> None:
    if not shap_vals:
        st.caption("SHAP values not available.")
        return

    features = [s["feature"] for s in shap_vals]
    contribs = [s["contribution"] for s in shap_vals]
    colors   = ["#10b981" if c >= 0 else "#f43f5e" for c in contribs]

    fig = go.Figure(go.Bar(
        x=contribs, y=features, orientation="h",
        marker=dict(color=colors),
        text=[f"{'+' if c>=0 else ''}{c:.3f}" for c in contribs],
        textposition="outside",
        textfont=dict(color="#94a3b8", size=10),
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color="#94a3b8", size=11),
        margin=dict(l=0, r=60, t=0, b=0), height=220,
        xaxis=dict(gridcolor="#1e2e52", zeroline=True, zerolinecolor="#334155"),
        yaxis=dict(gridcolor="rgba(0,0,0,0)"),
        showlegend=False,
    )
    st.plotly_chart(fig, width="stretch")


def _submit_decision(match_id: int, decision: str, reviewer: str, note: str,
                     match_obj: dict) -> None:
    """Persist decision and log to audit trail."""
    queries.update_match_decision(match_id, decision, reviewer, note)

    # If MERGED: create/update entity link
    if decision == "MERGED":
        import uuid
        from db.queries import create_entity, link_record_to_entity
        entity = {
            "ubid":            str(uuid.uuid4()),
            "canonical_name":  match_obj.get("name_a", ""),
            "pan":             match_obj.get("pan_a") or match_obj.get("pan_b"),
            "gstin":           match_obj.get("gstin_a") or match_obj.get("gstin_b"),
            "pin_code":        match_obj.get("pin_a"),
            "address":         match_obj.get("address_a"),
            "sector":          match_obj.get("sector_a"),
            "departments":     list({match_obj.get("dept_a"), match_obj.get("dept_b")} - {None}),
            "record_count":    2,
            "confidence_score": float(match_obj.get("confidence", 0.8)),
        }
        ubid = create_entity(entity)
        link_record_to_entity(ubid, str(match_obj["record_a_id"]), entity["confidence_score"], reviewer)
        link_record_to_entity(ubid, str(match_obj["record_b_id"]), entity["confidence_score"], reviewer)
        queries.execute(
            "UPDATE match_edges SET ubid_id = %s WHERE match_edge_id = %s",
            (ubid, match_id),
        )

    queries.log_audit(
        "REVIEWER_DECISION",
        f"{decision} — {note}",
        actor       = reviewer,
        match_id    = match_id,
        confidence  = float(match_obj.get("confidence", 0)),
        justification = note,
        before      = {"match_status": "REVIEW"},
        after       = {"match_status": decision},
    )
