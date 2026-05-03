"""
ApexForge AI — Database Query Layer

The original project used PostgreSQL, but this repository now ships with a
fully self-contained demo datastore so the app can run without external infra.
"""

from __future__ import annotations

from typing import Any
import os

from db.connection import execute, execute_many, execute_one, health_check, init_schema
from db.demo_store import get_store


def is_demo_mode() -> bool:
    return os.getenv("USE_DEMO_STORE", "true").strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# RAW RECORDS
# ---------------------------------------------------------------------------

def upsert_raw_record(record: dict) -> str:
    return get_store().upsert_raw_record(record)


def update_record_embedding(record_id: str, embedding: list[float]) -> None:
    get_store().update_record_embedding(record_id, embedding)


def get_records_by_department(dept_code: str, limit: int = 1000) -> list[dict]:
    return get_store().get_records_by_department(dept_code, limit)


def get_records_for_blocking(pin_code: str | None = None) -> list[dict]:
    return get_store().get_records_for_blocking(pin_code)


def get_unlinked_records() -> list[dict]:
    return get_store().get_unlinked_records()


def get_similar_records_by_embedding(embedding: list[float], top_k: int = 10, exclude_id: str | None = None) -> list[dict]:
    return get_store().get_similar_records_by_embedding(embedding, top_k, exclude_id)


# ---------------------------------------------------------------------------
# ENTITY MATCHES
# ---------------------------------------------------------------------------

def insert_match(match: dict) -> int | None:
    return get_store().insert_match(match)


def enqueue_review(match_id: int) -> None:
    get_store().enqueue_review(match_id)


def get_pending_matches(threshold: float = 0.65, limit: int = 50) -> list[dict]:
    return get_store().get_pending_matches(threshold, limit)


def update_match_decision(match_id: int, decision: str, reviewer: str, justification: str) -> None:
    get_store().update_match_decision(match_id, decision, reviewer, justification)


def get_graph_clusters_cte(seed_record_id: str) -> list[dict]:
    return get_store().get_graph_clusters_cte(seed_record_id)


def get_all_match_edges(status_filter: list[str] | None = None) -> list[dict]:
    return get_store().get_all_match_edges(status_filter)


def get_match_stats() -> dict:
    return get_store().get_match_stats()


# ---------------------------------------------------------------------------
# ENTITIES
# ---------------------------------------------------------------------------

def create_entity(entity: dict) -> str:
    return get_store().create_entity(entity)


def get_entity(ubid: str) -> dict | None:
    return get_store().get_entity(ubid)


def search_entities(query: str, pin_code: str | None = None, vitality: str | None = None, limit: int = 50) -> list[dict]:
    return get_store().search_entities(query, pin_code, vitality, limit)


def update_entity_vitality(ubid: str, status: str, score: float, pulse: int) -> None:
    get_store().update_entity_vitality(ubid, status, score, pulse)


def link_record_to_entity(ubid: str, record_id: str, confidence: float, linked_by: str = "system") -> None:
    get_store().link_record_to_entity(ubid, record_id, confidence, linked_by)


def get_entity_records(ubid: str) -> list[dict]:
    return get_store().get_entity_records(ubid)


def get_dashboard_stats() -> dict:
    return get_store().get_dashboard_stats()


def get_entities_by_sector(limit: int = 20) -> list[dict]:
    return get_store().get_entities_by_sector(limit)


def get_vitality_by_pin() -> list[dict]:
    return get_store().get_vitality_by_pin()


def get_active_entity_ids(limit: int = 5000) -> list[dict]:
    return get_store().get_active_entity_ids(limit)


def count_raw_records() -> int:
    return get_store().count_raw_records()


def count_entities() -> int:
    return get_store().count_entities()


def count_activity_events() -> int:
    return get_store().count_activity_events()


def count_audit_log() -> int:
    return get_store().count_audit_log()


def count_pending_reviews() -> int:
    return get_store().count_pending_reviews()


# ---------------------------------------------------------------------------
# ACTIVITY EVENTS
# ---------------------------------------------------------------------------

def insert_event(event: dict) -> None:
    get_store().insert_event(event)


def get_entity_events(ubid: str) -> list[dict]:
    return get_store().get_entity_events(ubid)


def get_vitality_signals(ubid: str) -> dict:
    return get_store().get_vitality_signals(ubid)


# ---------------------------------------------------------------------------
# AUDIT LOG
# ---------------------------------------------------------------------------

def log_audit(
    event_type: str,
    action: str,
    actor: str = "system",
    entity_ubid: str | None = None,
    match_id: int | None = None,
    before: dict | None = None,
    after: dict | None = None,
    confidence: float | None = None,
    justification: str | None = None,
) -> None:
    get_store().log_audit(
        event_type,
        action,
        actor=actor,
        entity_ubid=entity_ubid,
        match_id=match_id,
        before=before,
        after=after,
        confidence=confidence,
        justification=justification,
    )


def get_audit_trail(entity_ubid: str | None = None, limit: int = 100) -> list[dict]:
    return get_store().get_audit_trail(entity_ubid, limit)


# ---------------------------------------------------------------------------
# QUERY BUILDER / ACTIVE LEARNING
# ---------------------------------------------------------------------------

def run_structured_query(params: dict) -> list[dict]:
    return get_store().run_structured_query(params)


def get_learning_labels() -> list[dict]:
    return get_store().get_learning_labels()


def get_threshold_stats() -> dict:
    return get_store().get_threshold_stats()
