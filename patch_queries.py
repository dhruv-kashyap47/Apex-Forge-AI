import re
import os

with open('db/queries.py', 'r', encoding='utf-8') as f:
    code = f.read()

patches = {
    "def get_records_for_blocking(pin_code: str | None = None, limit: int = 100000) -> list[dict]:":
        """    if _DEMO_MODE:
        records = _get_store().get_records_for_blocking(pin_code)
        for r in records: r["normalized_record_id"] = r.get("id")
        return records""",
    "def get_unlinked_records(limit: int = 5000) -> list[dict]:":
        """    if _DEMO_MODE: return _get_store().get_unlinked_records()""",
    "def insert_match_edge(payload: dict) -> dict:":
        """    if _DEMO_MODE:
        match = {"record_a_id": payload.get("left_normalized_record_id"), "record_b_id": payload.get("right_normalized_record_id"), "confidence": payload.get("confidence", 0), "match_status": "AUTO_LINKED" if payload.get("decision_state") == "AUTO_MERGED" else ("REVIEW" if payload.get("decision_state") in ("PENDING", "IN_REVIEW") else "REJECTED"), "explanation": payload.get("explanation", {})}
        match_id = _get_store().insert_match(match)
        return {"match_edge_id": str(match_id), "decision_state": payload.get("decision_state")}""",
    "def enqueue_review(match_id: str) -> dict:":
        """    if _DEMO_MODE:
        try: mid = int(match_id)
        except: mid = hash(match_id) % 1_000_000
        _get_store().enqueue_review(mid)
        return {"match_edge_id": match_id}""",
    "def get_pending_matches(threshold: float = 0.65, limit: int = 50) -> list[dict]:":
        """    if _DEMO_MODE: return _get_store().get_pending_matches(threshold, limit)""",
    "def update_match_decision(match_id: str, decision: str, reviewer: str, justification: str, review_case_id: str | None = None) -> None:":
        """    if _DEMO_MODE:
        state = {"MERGED": "MERGED", "APPROVE": "MERGED", "SPLIT": "REJECTED", "REJECT": "REJECTED"}.get(decision.upper(), "REVIEW")
        try: mid = int(match_id)
        except: mid = hash(match_id) % 1_000_000
        _get_store().update_match_decision(mid, state, reviewer, justification)
        return""",
    "def create_cluster(payload: dict) -> dict:":
        """    if _DEMO_MODE: return {"cluster_id": "demo-cluster-" + str(uuid.uuid4())[:8]}""",
    "def create_cluster_member(payload: dict) -> dict:":
        """    if _DEMO_MODE: return payload""",
    "def create_ubid(payload: dict) -> dict:":
        """    if _DEMO_MODE:
        import uuid
        ubid = _get_store().create_entity({"canonical_name": payload.get("canonical_name"), "pan": payload.get("normalized_pan"), "gstin": payload.get("normalized_gstin"), "pin_code": payload.get("normalized_pin"), "sector": payload.get("summary", {}).get("sector"), "departments": payload.get("summary", {}).get("departments", []), "record_count": payload.get("record_count", 0), "confidence_score": 0.95, "vitality_status": "UNKNOWN", "vitality_score": 0.0, "pulse_score": 0})
        return {"ubid_id": ubid}""",
    "def link_record_to_ubid(ubid_id: str, normalized_record_id: str, confidence: float, linked_by: str = \"system\", match_edge_id: str | None = None, cluster_id: str | None = None) -> dict:":
        """    if _DEMO_MODE:
        _get_store().link_record_to_entity(ubid_id, normalized_record_id, confidence, linked_by)
        return {}""",
    "def update_entity_vitality(ubid: str, status: str, score: float, pulse: int, record_override: bool = True) -> None:":
        """    if _DEMO_MODE:
        _get_store().update_entity_vitality(ubid, status, score, pulse)
        return""",
    "def get_entity(ubid: str) -> dict | None:":
        """    if _DEMO_MODE: return _get_store().get_entity(ubid)""",
    "def search_entities(query: str, pin_code: str | None = None, vitality: str | None = None, limit: int = 50) -> list[dict]:":
        """    if _DEMO_MODE: return _get_store().search_entities(query, pin_code, vitality, limit)""",
    "def get_entity_records(ubid: str) -> list[dict]:":
        """    if _DEMO_MODE: return _get_store().get_entity_records(ubid)""",
    "def upsert_status_event(payload: dict) -> dict:":
        """    if _DEMO_MODE:
        _get_store().insert_event({"ubid": payload.get("ubid_id"), "raw_record_id": payload.get("raw_record_id"), "department_code": payload.get("event_source"), "event_type": payload.get("event_type"), "event_date": payload.get("event_date"), "signal_strength": payload.get("activity_weight", 1.0), "details": payload.get("details", {})})
        return {}""",
    "def get_entity_events(ubid: str) -> list[dict]:":
        """    if _DEMO_MODE: return _get_store().get_entity_events(ubid)""",
    "def get_active_entity_ids(limit: int = 5000) -> list[dict]:":
        """    if _DEMO_MODE: return _get_store().get_active_entity_ids(limit)""",
    "def get_vitality_signals(ubid: str) -> dict | None:":
        """    if _DEMO_MODE: return _get_store().get_vitality_signals(ubid)""",
    "def get_dashboard_stats() -> dict:":
        """    if _DEMO_MODE: return _get_store().get_dashboard_stats()""",
    "def get_entities_by_sector(limit: int = 20) -> list[dict]:":
        """    if _DEMO_MODE: return _get_store().get_entities_by_sector(limit)""",
    "def get_vitality_by_pin() -> list[dict]:":
        """    if _DEMO_MODE: return _get_store().get_vitality_by_pin()""",
    "def get_audit_trail(entity_ubid: str | None = None, limit: int = 100) -> list[dict]:":
        """    if _DEMO_MODE: return _get_store().get_audit_trail(entity_ubid, limit)""",
    "def count_audit_log() -> int:":
        """    if _DEMO_MODE: return _get_store().count_audit_log()""",
    "def get_threshold_stats() -> dict:":
        """    if _DEMO_MODE: return _get_store().get_threshold_stats()""",
    "def get_learning_labels() -> list[dict]:":
        """    if _DEMO_MODE: return _get_store().get_learning_labels()""",
    "def run_structured_query(params: dict) -> list[dict]:":
        """    if _DEMO_MODE: return _get_store().run_structured_query(params)""",
    "def get_review_cases(limit: int = 50) -> list[dict]:":
        """    if _DEMO_MODE: return _get_store().get_review_cases(limit)""",
    "def get_all_match_edges(status_filter: list[str] | None = None) -> list[dict]:":
        """    if _DEMO_MODE: return _get_store().get_all_match_edges(status_filter)""",
    "def get_match_stats() -> dict:":
        """    if _DEMO_MODE: return _get_store().get_match_stats()""",
}

for func_def, injected_code in patches.items():
    if func_def in code:
        if injected_code not in code:
            code = code.replace(func_def, func_def + "\n" + injected_code)

if "def log_audit(" not in code:
    code += """\n\ndef log_audit(event_type: str, action: str, actor: str = "system", entity_ubid: str | None = None, match_id: int | None = None, before: dict | None = None, after: dict | None = None, confidence: float | None = None, justification: str | None = None, **kwargs) -> None:\n    if _DEMO_MODE: return _get_store().log_audit(event_type, action, actor, entity_ubid, match_id, before, after, confidence, justification)\n"""

with open('db/queries.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("Patched db/queries.py successfully.")
