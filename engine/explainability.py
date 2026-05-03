from __future__ import annotations

from typing import Any


def _pct(v: float) -> str:
    return f"{round(v * 100)}%"


def _strength(v: float) -> str:
    if v >= 0.85:
        return "very high"
    if v >= 0.70:
        return "high"
    if v >= 0.50:
        return "moderate"
    if v >= 0.30:
        return "low"
    return "very low"


def _level(label: str, value: float) -> dict:
    return {"label": label, "value": round(value, 3), "strength": _strength(value)}


def generate_explanation(pair: dict) -> dict:
    signals: list[dict] = []
    reasons: list[str] = []
    concerns: list[str] = []

    if pair.get("pan_match"):
        signals.append({"signal": "PAN Match", "value": 1.0, "strength": "definitive"})
        reasons.append("PAN numbers are identical, which is a strong deterministic identifier.")
    if pair.get("gstin_match"):
        signals.append({"signal": "GSTIN Match", "value": 1.0, "strength": "definitive"})
        reasons.append("GSTIN numbers are identical, which usually means the same registration.")

    ph = float(pair.get("name_phonetic_score", 0))
    fz = float(pair.get("name_fuzzy_score", 0))
    em = float(pair.get("embedding_score", 0))
    pm = bool(pair.get("pin_match"))
    ad = float(pair.get("address_score", 0))
    gb = float(pair.get("graph_boost", 0))

    if ph > 0:
        signals.append(_level("Phonetic Name Match", ph))
    if fz > 0:
        signals.append(_level("Fuzzy Name Score", fz))
    if em > 0:
        signals.append(_level("Semantic Similarity", em))
    if pm:
        signals.append({"signal": "PIN Code Match", "value": 1.0, "strength": "strong"})
        reasons.append("Both records share the same PIN code.")
    if ad > 0:
        signals.append(_level("Address Similarity", ad))
    if gb > 0:
        signals.append(_level("Graph Boost", gb))

    confidence = float(pair.get("confidence", 0))
    status = pair.get("match_status", "REVIEW")
    if status == "AUTO_LINKED":
        verdict = f"System auto-linked this pair with {_pct(confidence)} confidence."
    elif status == "REVIEW":
        verdict = f"System flagged this pair for human review with {_pct(confidence)} confidence."
    else:
        verdict = f"System rejected this pair with {_pct(confidence)} confidence."

    if not reasons and status == "REVIEW":
        reasons.append("The records share enough features to warrant manual inspection.")
    if not concerns and status == "REJECTED":
        concerns.append("The evidence does not meet the review threshold.")

    return {
        "verdict": verdict,
        "confidence": round(confidence, 4),
        "status": status,
        "signals": signals,
        "reasons": reasons,
        "concerns": concerns,
        "weights_used": {
            "note": "Heuristic ensemble tuned for blocking-based resolution",
        },
    }


def compute_shap_values(pair: dict) -> list[dict]:
    features = [
        ("PAN Match", float(bool(pair.get("pan_match")))),
        ("GSTIN Match", float(bool(pair.get("gstin_match")))),
        ("Phonetic Name", float(pair.get("name_phonetic_score", 0))),
        ("Fuzzy Name", float(pair.get("name_fuzzy_score", 0))),
        ("Semantic Similarity", float(pair.get("embedding_score", 0))),
        ("PIN Code", float(bool(pair.get("pin_match")))),
        ("Address Similarity", float(pair.get("address_score", 0))),
        ("Graph Boost", float(pair.get("graph_boost", 0))),
    ]
    total = sum(value for _, value in features) or 1.0
    return [
        {
            "feature": feature,
            "raw_value": value,
            "contribution": round(value / total, 4),
            "direction": "positive" if value >= 0 else "negative",
        }
        for feature, value in sorted(features, key=lambda item: item[1], reverse=True)
    ]


def explain_vitality(signals: dict, status: str, score: float, pulse: int) -> dict:
    reasons: list[str] = []
    concerns: list[str] = []

    ev6 = int(signals.get("events_6m", 0))
    ev12 = int(signals.get("events_12m", 0))
    ev18 = int(signals.get("events_18m", 0))
    ren = int(signals.get("renewals", 0))
    ins = int(signals.get("inspections", 0))
    fil = int(signals.get("filings", 0))
    shut = int(signals.get("shutdowns", 0))
    last = signals.get("last_event")

    if shut > 0:
        concerns.append(f"{shut} shutdown event(s) detected.")
    if ren > 0:
        reasons.append(f"{ren} renewal event(s) detected.")
    if ins > 0:
        reasons.append(f"{ins} inspection event(s) detected.")
    if fil > 0:
        reasons.append(f"{fil} filing event(s) detected.")
    if ev6 > 0:
        reasons.append(f"{ev6} event(s) in the last 6 months.")
    elif ev12 > 0:
        reasons.append(f"{ev12} event(s) in the last 12 months.")
    elif ev18 > 0:
        concerns.append(f"Last activity was 6-18 months ago.")
    else:
        concerns.append("No recent activity detected.")
    if last:
        reasons.append(f"Last recorded event: {str(last)[:10]}.")

    status_desc = {
        "ACTIVE": f"ACTIVE - Pulse {pulse}/100.",
        "DORMANT": f"DORMANT - Pulse {pulse}/100.",
        "CLOSED": f"CLOSED - Pulse {pulse}/100.",
        "UNKNOWN": f"UNKNOWN - Pulse {pulse}/100.",
    }.get(status, f"{status} - Pulse {pulse}/100.")

    return {
        "status": status,
        "vitality_score": round(score, 4),
        "pulse_score": pulse,
        "status_desc": status_desc,
        "reasons": reasons,
        "concerns": concerns,
        "model_note": "Temporal activity analysis over status events.",
    }

