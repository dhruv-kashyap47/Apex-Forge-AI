from __future__ import annotations

from datetime import datetime, timezone
import math

from loguru import logger

from db import queries

EVENT_WEIGHTS = {
    "RENEWAL": 1.0,
    "INSPECTION": 0.9,
    "FILING": 0.8,
    "UTILITY": 0.7,
    "COMPLAINT": 0.3,
    "SHUTDOWN": -2.0,
}


def _time_decay(event_date: datetime | str | None, half_life_days: int = 180) -> float:
    if not event_date:
        return 0.0
    if isinstance(event_date, str):
        try:
            event_date = datetime.fromisoformat(event_date.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
    if type(event_date).__name__ == "date":
        event_date = datetime.combine(event_date, datetime.min.time())
    if event_date.tzinfo is None:
        event_date = event_date.replace(tzinfo=timezone.utc)
    days_ago = max((datetime.now(timezone.utc) - event_date).days, 0)
    return math.exp(-(math.log(2) / half_life_days) * days_ago)


def compute_vitality(ubid: str, events: list[dict] | None = None) -> dict:
    if events is None:
        events = queries.get_entity_events(ubid)
    signals = queries.get_vitality_signals(ubid)
    shutdown_count = int(signals.get("shutdowns", 0))
    renewal_count = int(signals.get("renewals", 0))
    events_6m = int(signals.get("events_6m", 0))
    events_12m = int(signals.get("events_12m", 0))
    events_18m = int(signals.get("events_18m", 0))
    total_events = int(signals.get("total_events", 0))

    weighted_sum = 0.0
    for ev in events:
        weighted_sum += EVENT_WEIGHTS.get(ev.get("event_type"), 0.5) * _time_decay(ev.get("event_date"))
    vitality_score = min(weighted_sum / max(len(events), 1), 1.0) if events else 0.0

    if shutdown_count > 0:
        status = "CLOSED"
        vitality_score = max(vitality_score * 0.1, 0.02)
    elif total_events == 0:
        status = "UNKNOWN"
    elif events_6m >= 2 or renewal_count >= 1 or events_12m >= 2:
        status = "ACTIVE"
    elif events_18m >= 1 or total_events > 0:
        status = "DORMANT"
    else:
        status = "UNKNOWN"

    event_types_seen = list({ev.get("event_type") for ev in events if ev.get("event_type")})
    recency_last = _time_decay(signals.get("last_event"))
    diversity_bonus = min(len(event_types_seen) / max(len(EVENT_WEIGHTS), 1), 1.0)
    pulse = max(0, min(100, round(vitality_score * 70 + recency_last * 20 + diversity_bonus * 10)))

    return {
        "ubid": ubid,
        "status": status,
        "vitality_score": round(vitality_score, 4),
        "pulse_score": pulse,
        "signals": signals,
        "breakdown": {
            "weighted_sum": round(weighted_sum, 4),
            "decay_factor": round(recency_last, 4),
            "diversity_bonus": round(diversity_bonus, 4),
            "event_count": total_events,
            "event_types": event_types_seen,
        },
    }


def classify_all_entities(limit: int = 5000) -> dict:
    entities = queries.get_active_entity_ids(limit)
    updated = 0
    for ent in entities:
        ubid = str(ent["ubid"])
        result = compute_vitality(ubid)
        queries.update_entity_vitality(ubid, result["status"], result["vitality_score"], result["pulse_score"], record_override=False)
        queries.log_audit(
            "VITALITY_UPDATED",
            f"Classification: {result['status']} (pulse={result['pulse_score']})",
            entity_ubid=ubid,
            confidence=result["vitality_score"],
            after={"status": result["status"], "pulse": result["pulse_score"]},
            entity_type="UBID",
        )
        updated += 1
    logger.info("Vitality classification complete: {} entities updated.", updated)
    return {"entities_classified": updated}


def survival_trend(ubid: str) -> list[dict]:
    events = queries.get_entity_events(ubid)
    result = []
    for i, ev in enumerate(sorted(events, key=lambda e: str(e.get("event_date") or ""))):
        etype = ev.get("event_type", "UNKNOWN")
        result.append(
            {
                "date": str(ev.get("event_date"))[:10] if ev.get("event_date") else "N/A",
                "event_type": etype,
                "survival": round(_time_decay(ev.get("event_date")), 4),
                "signal_weight": EVENT_WEIGHTS.get(etype, 0.5),
                "cumulative_index": i + 1,
            }
        )
    return result
