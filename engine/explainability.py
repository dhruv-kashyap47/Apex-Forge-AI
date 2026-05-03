"""
ApexForge AI — Explainability Engine
Generates human-readable, SHAP-style justifications for every match decision.
No black boxes. Every score is traceable to individual signals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ─── Signal thresholds for natural language ───────────────────────────────

def _pct(v: float) -> str:
    return f"{round(v * 100)}%"


def _strength(v: float) -> str:
    if v >= 0.85: return "very high"
    if v >= 0.70: return "high"
    if v >= 0.50: return "moderate"
    if v >= 0.30: return "low"
    return "very low"


def _level(label: str, value: float) -> dict:
    return {"label": label, "value": round(value, 3), "strength": _strength(value)}


# ═══════════════════════════════════════════════════════════════════════════
# NATURAL LANGUAGE JUSTIFICATION
# ═══════════════════════════════════════════════════════════════════════════

def generate_explanation(pair: dict) -> dict:
    """
    Build a structured explanation dict for a matched pair.
    Stored in entity_matches.explanation (JSONB).
    """
    signals: list[dict] = []
    reasons: list[str]  = []
    concerns: list[str] = []

    # ── Deterministic anchors ─────────────────────────────────────────────
    if pair.get("pan_match"):
        signals.append({"signal": "PAN Match", "value": 1.0, "strength": "definitive"})
        reasons.append("PAN numbers are identical — this is a definitive government identifier match.")

    if pair.get("gstin_match"):
        signals.append({"signal": "GSTIN Match", "value": 1.0, "strength": "definitive"})
        reasons.append("GSTIN numbers are identical — confirmed same tax registration.")

    # ── Soft signals ──────────────────────────────────────────────────────
    ph = float(pair.get("name_phonetic_score", 0))
    fz = float(pair.get("name_fuzzy_score", 0))
    em = float(pair.get("embedding_score", 0))
    pm = bool(pair.get("pin_match"))
    ad = float(pair.get("address_score", 0))
    gb = float(pair.get("graph_boost", 0))

    if ph > 0:
        signals.append(_level("Phonetic Name Match", ph))
        if ph >= 0.8:
            reasons.append(f"Business names sound phonetically identical ({_pct(ph)} match) — "
                           "consistent with transliteration variation (e.g. Kannada/English).")
        elif ph >= 0.5:
            reasons.append(f"Phonetic similarity is moderate ({_pct(ph)}) — possible abbreviation.")

    if fz > 0:
        signals.append(_level("Fuzzy Name Score", fz))
        if fz >= 0.85:
            reasons.append(f"Name character similarity is very high ({_pct(fz)}) after normalisation.")
        elif fz >= 0.65:
            reasons.append(f"Names share {_pct(fz)} character-level similarity — likely same entity.")
        else:
            concerns.append(f"Name fuzzy score is only {_pct(fz)} — verify manually.")

    if em > 0:
        signals.append(_level("Semantic Embedding", em))
        if em >= 0.85:
            reasons.append(f"Semantic embedding similarity is {_pct(em)} — "
                           "records describe the same type of business in the same context.")
        elif em >= 0.70:
            reasons.append(f"Embedding similarity ({_pct(em)}) suggests related business profiles.")
        else:
            concerns.append(f"Embedding similarity is low ({_pct(em)}) — different business contexts.")

    if pm:
        signals.append({"signal": "PIN Code Match", "value": 1.0, "strength": "strong"})
        reasons.append("Both records share the same PIN code — same geographic area.")
    else:
        concerns.append("PIN codes differ — could indicate a branch or data entry error.")

    if ad > 0.5:
        signals.append(_level("Address Similarity", ad))
        reasons.append(f"Address strings overlap by {_pct(ad)} — consistent location.")
    elif ad > 0:
        signals.append(_level("Address Similarity", ad))
        if ad < 0.3:
            concerns.append(f"Address similarity is very low ({_pct(ad)}) — check for branch locations.")

    if gb > 0.1:
        signals.append(_level("Graph Propagation Boost", gb))
        reasons.append(f"Transitive graph analysis added +{_pct(gb)} boost — "
                       "other confirmed links suggest these records belong to the same cluster.")

    # ── Composite summary ─────────────────────────────────────────────────
    confidence  = float(pair.get("confidence", 0))
    status      = pair.get("match_status", "REVIEW")

    if status == "AUTO_LINKED":
        verdict = (f"System AUTO-LINKED these records with {_pct(confidence)} confidence. "
                   "No human review required.")
    elif status == "REVIEW":
        verdict = (f"System flagged for HUMAN REVIEW ({_pct(confidence)} confidence). "
                   "Please examine the signals and press Merge or Split.")
    else:
        verdict = (f"System REJECTED this pair ({_pct(confidence)} confidence — below threshold). "
                   "Records are likely different entities.")

    return {
        "verdict":    verdict,
        "confidence": round(confidence, 4),
        "status":     status,
        "signals":    signals,
        "reasons":    reasons,
        "concerns":   concerns,
        "weights_used": {
            "note":   "Bayesian ensemble of signals",
            "pan":    "35% weight (deterministic anchor)",
            "gstin":  "30% weight (deterministic anchor)",
            "name":   "20% weight (phonetic + fuzzy split)",
            "embed":  "20% weight (semantic context)",
            "pin":    "5% weight (geographic)",
            "addr":   "5% weight (location detail)",
            "graph":  "10% weight (network propagation)",
        }
    }


# ═══════════════════════════════════════════════════════════════════════════
# SHAP-STYLE FEATURE IMPORTANCE
# ═══════════════════════════════════════════════════════════════════════════

def compute_shap_values(pair: dict) -> list[dict]:
    """
    Compute marginal contribution of each signal to the final confidence score.
    Approximates SHAP with leave-one-out sensitivity analysis.
    Returns list of {feature, value, contribution, direction}.
    """
    from engine.resolver import compute_confidence, MatchSignals, WEIGHTS

    def _sig_from_pair(p: dict, exclude: str | None = None) -> MatchSignals:
        s = MatchSignals(
            pan_match            = False if exclude == "pan"     else bool(p.get("pan_match")),
            gstin_match          = False if exclude == "gstin"   else bool(p.get("gstin_match")),
            name_phonetic_score  = 0.0  if exclude == "phonetic" else float(p.get("name_phonetic_score",0)),
            name_fuzzy_score     = 0.0  if exclude == "fuzzy"    else float(p.get("name_fuzzy_score",0)),
            embedding_score      = 0.0  if exclude == "embed"    else float(p.get("embedding_score",0)),
            pin_match            = False if exclude == "pin"      else bool(p.get("pin_match")),
            address_score        = 0.0  if exclude == "address"  else float(p.get("address_score",0)),
            graph_boost          = 0.0  if exclude == "graph"    else float(p.get("graph_boost",0)),
        )
        return s

    baseline = compute_confidence(_sig_from_pair(pair))
    features = ["pan", "gstin", "phonetic", "fuzzy", "embed", "pin", "address", "graph"]
    labels = {
        "pan":      "PAN Match",
        "gstin":    "GSTIN Match",
        "phonetic": "Phonetic Name",
        "fuzzy":    "Fuzzy Name",
        "embed":    "Semantic Embedding",
        "pin":      "PIN Code",
        "address":  "Address Similarity",
        "graph":    "Graph Boost",
    }
    result = []
    for feat in features:
        without = compute_confidence(_sig_from_pair(pair, exclude=feat))
        contribution = round(baseline - without, 4)
        result.append({
            "feature":      labels[feat],
            "raw_value":    float(pair.get(feat + "_match", pair.get(feat, pair.get(feat + "_score", 0))) or 0),
            "contribution": contribution,
            "direction":    "positive" if contribution >= 0 else "negative",
        })

    return sorted(result, key=lambda x: abs(x["contribution"]), reverse=True)


# ═══════════════════════════════════════════════════════════════════════════
# VITALITY EXPLANATION
# ═══════════════════════════════════════════════════════════════════════════

def explain_vitality(signals: dict, status: str, score: float, pulse: int) -> dict:
    """Generate natural-language explanation for a vitality classification."""
    reasons: list[str] = []
    concerns: list[str] = []

    ev6  = int(signals.get("events_6m", 0))
    ev12 = int(signals.get("events_12m", 0))
    ev18 = int(signals.get("events_18m", 0))
    ren  = int(signals.get("renewals", 0))
    ins  = int(signals.get("inspections", 0))
    fil  = int(signals.get("filings", 0))
    shut = int(signals.get("shutdowns", 0))
    last = signals.get("last_event")

    if shut > 0:
        concerns.append(f"⚠ {shut} shutdown event(s) detected — strong indicator of closure.")
    if ren > 0:
        reasons.append(f"✓ {ren} license renewal event(s) — active compliance signal.")
    if ins > 0:
        reasons.append(f"✓ {ins} inspection event(s) — government engagement confirms presence.")
    if fil > 0:
        reasons.append(f"✓ {fil} filing event(s) — regulatory submissions are recent.")
    if ev6 > 0:
        reasons.append(f"✓ {ev6} activity events in last 6 months — strong activity signal.")
    elif ev12 > 0:
        reasons.append(f"△ {ev12} events in last 12 months but none in last 6 — watch closely.")
    elif ev18 > 0:
        concerns.append(f"⚠ Last activity was 6-18 months ago ({ev18} events) — possible dormancy.")
    else:
        concerns.append("⚠ No recent activity detected in 18+ months — likely dormant or closed.")

    if last:
        reasons.append(f"↻ Last recorded event: {str(last)[:10]}.")

    status_desc = {
        "ACTIVE":  f"ACTIVE — Business shows strong operational signals (Pulse: {pulse}/100).",
        "DORMANT": f"DORMANT — Activity has stalled; at risk of closure (Pulse: {pulse}/100).",
        "CLOSED":  f"CLOSED — Shutdown signals detected or no activity for 18+ months (Pulse: {pulse}/100).",
        "UNKNOWN": f"UNKNOWN — Insufficient data to classify (Pulse: {pulse}/100).",
    }.get(status, f"{status} (Pulse: {pulse}/100)")

    return {
        "status":      status,
        "vitality_score": round(score, 4),
        "pulse_score": pulse,
        "status_desc": status_desc,
        "reasons":     reasons,
        "concerns":    concerns,
        "model_note":  (
            "Classification uses temporal event analysis: "
            "recent renewals & inspections → ACTIVE; "
            "long gaps in events → DORMANT; "
            "explicit shutdown events → CLOSED. "
            "Pulse Score = weighted decay of recency × event diversity."
        )
    }
