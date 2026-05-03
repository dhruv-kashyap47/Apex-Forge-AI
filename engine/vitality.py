"""
ApexForge AI — Business Vitality Engine
Classifies businesses as ACTIVE | DORMANT | CLOSED using temporal event analysis.
Also computes the Vitality Pulse Score (0-100) — a near-term risk metric.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from loguru import logger

from db import queries


# ─── Decay function ──────────────────────────────────────────────────────────
# More recent events contribute more to vitality score.

def _time_decay(event_date: datetime | str | None, half_life_days: int = 180) -> float:
    """Exponential time-decay: signal = e^(-λt) where λ = ln(2)/half_life."""
    if not event_date:
        return 0.0
    if isinstance(event_date, str):
        try:
            event_date = datetime.fromisoformat(event_date)
        except ValueError:
            return 0.0
    now = datetime.now(timezone.utc)
    if event_date.tzinfo is None:
        event_date = event_date.replace(tzinfo=timezone.utc)
    days_ago = max((now - event_date).days, 0)
    lam = math.log(2) / half_life_days
    return math.exp(-lam * days_ago)


# ─── Event type weights ───────────────────────────────────────────────────────
EVENT_WEIGHTS = {
    "RENEWAL":    1.0,   # License renewal = strongest signal
    "INSPECTION": 0.9,   # Government inspected = present & operating
    "FILING":     0.8,   # Regulatory filing = compliance active
    "UTILITY":    0.7,   # Utility consumption = physical operations
    "COMPLAINT":  0.3,   # Complaints = presence but issues
    "SHUTDOWN":  -2.0,   # Shutdown notice = heavy negative
}


# ═══════════════════════════════════════════════════════════════════════════
# VITALITY SCORING
# ═══════════════════════════════════════════════════════════════════════════

def compute_vitality(ubid: str, events: list[dict] | None = None) -> dict:
    """
    Compute vitality status, score, and pulse for a single entity.

    Returns:
        {status, vitality_score, pulse_score, signals, breakdown}
    """
    if events is None:
        events = queries.get_entity_events(ubid)

    signals = queries.get_vitality_signals(ubid)

    # ── Raw scores ────────────────────────────────────────────────────────
    shutdown_count = int(signals.get("shutdowns", 0))
    renewal_count  = int(signals.get("renewals",  0))
    events_6m      = int(signals.get("events_6m", 0))
    events_12m     = int(signals.get("events_12m",0))
    events_18m     = int(signals.get("events_18m",0))
    total_events   = int(signals.get("total_events", 0))

    # ── Temporal weighted score ───────────────────────────────────────────
    weighted_sum = 0.0
    for ev in events:
        etype  = ev.get("event_type", "")
        edate  = ev.get("event_date")
        weight = EVENT_WEIGHTS.get(etype, 0.5)
        decay  = _time_decay(edate)
        weighted_sum += weight * decay

    # Normalise to [0, 1]
    if events:
        max_possible  = len(events) * max(EVENT_WEIGHTS.values())
        vitality_score = min(weighted_sum / max(max_possible, 1), 1.0)
    else:
        vitality_score = 0.0

    # ── Hard rules ────────────────────────────────────────────────────────
    if shutdown_count > 0:
        status = "CLOSED"
        vitality_score = max(vitality_score * 0.1, 0.02)

    elif total_events == 0:
        status = "UNKNOWN"
        vitality_score = 0.0

    elif events_6m >= 2 or (renewal_count >= 1 and events_12m >= 1):
        status = "ACTIVE"

    elif events_12m >= 1:
        # Some activity in past year but less than 6 months
        status = "ACTIVE" if vitality_score >= 0.4 else "DORMANT"

    elif events_18m >= 1:
        status = "DORMANT"
        vitality_score = min(vitality_score, 0.35)

    elif total_events > 0:
        status = "DORMANT"
        vitality_score = min(vitality_score, 0.20)

    else:
        status = "UNKNOWN"
        vitality_score = 0.0

    # ── Pulse Score (0-100) ────────────────────────────────────────────────
    # Pulse = (vitality_score × 70) + (recency_bonus × 20) + (diversity_bonus × 10)
    event_types_seen = list(set(ev.get("event_type") for ev in events))
    diversity_bonus  = min(len(event_types_seen) / max(len(EVENT_WEIGHTS), 1), 1.0)
    recency_last     = _time_decay(signals.get("last_event"))

    pulse = (
        vitality_score  * 70 +
        recency_last    * 20 +
        diversity_bonus * 10
    )
    pulse_score = max(0, min(100, round(pulse)))

    return {
        "ubid":           ubid,
        "status":         status,
        "vitality_score": round(vitality_score, 4),
        "pulse_score":    pulse_score,
        "signals":        signals,
        "breakdown": {
            "weighted_sum":    round(weighted_sum, 4),
            "decay_factor":    round(recency_last, 4),
            "diversity_bonus": round(diversity_bonus, 4),
            "event_count":     total_events,
            "event_types":     event_types_seen,
        }
    }


def classify_all_entities(limit: int = 5000) -> dict:
    """
    Batch-classify all entities. Runs on startup and can be re-triggered.
    """
    entities = queries.get_active_entity_ids(limit)
    updated = 0
    for ent in entities:
        ubid = str(ent["ubid"])
        result = compute_vitality(ubid)
        queries.update_entity_vitality(
            ubid,
            result["status"],
            result["vitality_score"],
            result["pulse_score"],
        )
        queries.log_audit(
            "VITALITY_UPDATED",
            f"Classification: {result['status']} (pulse={result['pulse_score']})",
            entity_ubid = ubid,
            confidence  = result["vitality_score"],
            after       = {"status": result["status"], "pulse": result["pulse_score"]},
        )
        updated += 1

    logger.info(f"Vitality classification complete: {updated} entities updated.")
    return {"entities_classified": updated}


# ═══════════════════════════════════════════════════════════════════════════
# KAPLAN-MEIER SURVIVAL PROXY (Vitality Pulse Trend)
# ═══════════════════════════════════════════════════════════════════════════

def survival_trend(ubid: str) -> list[dict]:
    """
    Approximate Kaplan-Meier survival curve using event timestamps.
    Returns a time-series of "survival probability" for chart rendering.
    """
    events = queries.get_entity_events(ubid)
    if not events:
        return []

    events_sorted = sorted(events, key=lambda e: str(e.get("event_date") or ""))
    now = datetime.now(timezone.utc)
    result = []

    for i, ev in enumerate(events_sorted):
        edate = ev.get("event_date")
        decay = _time_decay(edate)
        etype = ev.get("event_type", "UNKNOWN")
        result.append({
            "date":       str(edate)[:10] if edate else "N/A",
            "event_type": etype,
            "survival":   round(decay, 4),
            "signal_weight": EVENT_WEIGHTS.get(etype, 0.5),
            "cumulative_index": i + 1,
        })

    return result
