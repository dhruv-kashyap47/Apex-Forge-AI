from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any
import json
import os
import uuid

try:
    from psycopg.types.json import Jsonb
except ImportError as exc:  # pragma: no cover - surfaced at runtime
    Jsonb = None
    _JSON_IMPORT_ERROR = exc

from db.connection import execute, execute_one, execute_many, health_check, init_schema


def is_demo_mode() -> bool:
    return False


def _json(value: Any):
    if Jsonb is None:
        raise ModuleNotFoundError("A PostgreSQL driver is required. Install 'psycopg[binary]'.") from _JSON_IMPORT_ERROR
    return Jsonb(value)


def _uuid_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _ensure_schema() -> None:
    # Safe to call repeatedly; CREATE IF NOT EXISTS guards schema bootstrap.
    init_schema()


# ---------------------------------------------------------------------------
# Bootstrap / health
# ---------------------------------------------------------------------------

def bootstrap() -> None:
    _ensure_schema()


def ping() -> bool:
    return health_check()


# ---------------------------------------------------------------------------
# Processing runs
# ---------------------------------------------------------------------------

def create_processing_run(run_type: str, triggered_by: str = "system", triggered_by_user: str | None = None, parameters: dict | None = None, parent_run_id: str | None = None) -> dict:
    row = execute_one(
        """
        INSERT INTO processing_runs (run_type, triggered_by, triggered_by_user, parameters, parent_run_id, status, started_at)
        VALUES (%s, %s, %s, %s, %s, 'RUNNING', NOW())
        RETURNING *
        """,
        (run_type, triggered_by, triggered_by_user, _json(parameters or {}), parent_run_id),
    )
    return row or {}


def finish_processing_run(run_id: str, status: str, metrics: dict | None = None, error_message: str | None = None) -> None:
    execute(
        """
        UPDATE processing_runs
        SET status = %s,
            metrics = COALESCE(%s, metrics),
            error_message = %s,
            finished_at = CASE WHEN %s IN ('SUCCEEDED','FAILED','CANCELLED') THEN NOW() ELSE finished_at END
        WHERE run_id = %s
        """,
        (status, _json(metrics or {}), error_message, status, run_id),
    )


def get_latest_processing_runs(limit: int = 20) -> list[dict]:
    return execute(
        """
        SELECT *
        FROM processing_runs
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )


# ---------------------------------------------------------------------------
# Uploads / source files / records
# ---------------------------------------------------------------------------

def create_upload(payload: dict) -> dict:
    row = execute_one(
        """
        INSERT INTO uploads (
            processing_run_id, uploader_id, uploader_name, department_code, dataset_name,
            original_filename, content_type, file_format, file_size_bytes, content_sha256,
            upload_status, schema_mapping, parse_summary, validation_summary,
            source_row_count, valid_row_count, rejected_row_count
        )
        VALUES (%(processing_run_id)s, %(uploader_id)s, %(uploader_name)s, %(department_code)s, %(dataset_name)s,
                %(original_filename)s, %(content_type)s, %(file_format)s, %(file_size_bytes)s, %(content_sha256)s,
                %(upload_status)s, %(schema_mapping)s, %(parse_summary)s, %(validation_summary)s,
                %(source_row_count)s, %(valid_row_count)s, %(rejected_row_count)s)
        ON CONFLICT (content_sha256) DO UPDATE SET
            updated_at = NOW()
        RETURNING *
        """,
        {
            **payload,
            "schema_mapping": _json(payload.get("schema_mapping") or {}),
            "parse_summary": _json(payload.get("parse_summary") or {}),
            "validation_summary": _json(payload.get("validation_summary") or {}),
        },
    )
    return row or {}


def update_upload(upload_id: str, **fields: Any) -> None:
    if not fields:
        return
    assignments = ", ".join(f"{key} = %s" for key in fields)
    values = list(fields.values()) + [upload_id]
    execute(f"UPDATE uploads SET {assignments} WHERE upload_id = %s", tuple(values))


def create_source_file(payload: dict) -> dict:
    row = execute_one(
        """
        INSERT INTO source_files (
            upload_id, file_index, source_name, source_format, original_filename,
            source_checksum, source_metadata, file_status
        )
        VALUES (%(upload_id)s, %(file_index)s, %(source_name)s, %(source_format)s, %(original_filename)s,
                %(source_checksum)s, %(source_metadata)s, %(file_status)s)
        ON CONFLICT (upload_id, file_index) DO UPDATE SET
            source_name = EXCLUDED.source_name,
            source_format = EXCLUDED.source_format,
            original_filename = EXCLUDED.original_filename,
            source_checksum = EXCLUDED.source_checksum,
            source_metadata = EXCLUDED.source_metadata,
            file_status = EXCLUDED.file_status,
            updated_at = NOW()
        RETURNING *
        """,
        {
            **payload,
            "source_metadata": _json(payload.get("source_metadata") or {}),
        },
    )
    return row or {}


def insert_raw_record(record: dict) -> dict:
    row = execute_one(
        """
        INSERT INTO raw_records (
            source_file_id, processing_run_id, source_row_number, source_record_key, department_code,
            raw_payload, raw_text, ingestion_state, validation_errors, mapping_warnings,
            mapping_confidence, is_duplicate, record_hash, business_name, trade_name, legal_name,
            pan, gstin, pin_code, district, state, city, address_line1, address_line2,
            address_full, activity_date, registration_date, last_activity_date, source_status,
            source_category, sector, extra_fields
        )
        VALUES (
            %(source_file_id)s, %(processing_run_id)s, %(source_row_number)s, %(source_record_key)s, %(department_code)s,
            %(raw_payload)s, %(raw_text)s, %(ingestion_state)s, %(validation_errors)s, %(mapping_warnings)s,
            %(mapping_confidence)s, %(is_duplicate)s, %(record_hash)s, %(business_name)s, %(trade_name)s, %(legal_name)s,
            %(pan)s, %(gstin)s, %(pin_code)s, %(district)s, %(state)s, %(city)s, %(address_line1)s, %(address_line2)s,
            %(address_full)s, %(activity_date)s, %(registration_date)s, %(last_activity_date)s, %(source_status)s,
            %(source_category)s, %(sector)s, %(extra_fields)s
        )
        ON CONFLICT (record_hash) DO UPDATE SET
            raw_payload = EXCLUDED.raw_payload,
            raw_text = EXCLUDED.raw_text,
            ingestion_state = EXCLUDED.ingestion_state,
            validation_errors = EXCLUDED.validation_errors,
            mapping_warnings = EXCLUDED.mapping_warnings,
            mapping_confidence = EXCLUDED.mapping_confidence,
            is_duplicate = EXCLUDED.is_duplicate,
            business_name = EXCLUDED.business_name,
            trade_name = EXCLUDED.trade_name,
            legal_name = EXCLUDED.legal_name,
            pan = EXCLUDED.pan,
            gstin = EXCLUDED.gstin,
            pin_code = EXCLUDED.pin_code,
            district = EXCLUDED.district,
            state = EXCLUDED.state,
            city = EXCLUDED.city,
            address_line1 = EXCLUDED.address_line1,
            address_line2 = EXCLUDED.address_line2,
            address_full = EXCLUDED.address_full,
            activity_date = EXCLUDED.activity_date,
            registration_date = EXCLUDED.registration_date,
            last_activity_date = EXCLUDED.last_activity_date,
            source_status = EXCLUDED.source_status,
            source_category = EXCLUDED.source_category,
            sector = EXCLUDED.sector,
            extra_fields = EXCLUDED.extra_fields,
            updated_at = NOW()
        RETURNING *
        """,
        {
            **record,
            "raw_payload": _json(record.get("raw_payload") or {}),
            "validation_errors": _json(record.get("validation_errors") or []),
            "mapping_warnings": _json(record.get("mapping_warnings") or []),
            "extra_fields": _json(record.get("extra_fields") or {}),
        },
    )
    return row or {}


def insert_raw_records(records: list[dict]) -> list[dict]:
    return [insert_raw_record(record) for record in records]


def insert_normalized_record(record: dict) -> dict:
    row = execute_one(
        """
        INSERT INTO normalized_records (
            raw_record_id, processing_run_id, record_hash, canonical_name, canonical_name_key,
            name_tokens, phonetic_key, name_bucket, normalized_pan, normalized_gstin, normalized_pin,
            normalized_district, normalized_state, normalized_city, normalized_address, address_key,
            entity_type, sector, confidence, source_flags, feature_payload, normalizer_version, name_embedding
        )
        VALUES (
            %(raw_record_id)s, %(processing_run_id)s, %(record_hash)s, %(canonical_name)s, %(canonical_name_key)s,
            %(name_tokens)s, %(phonetic_key)s, %(name_bucket)s, %(normalized_pan)s, %(normalized_gstin)s, %(normalized_pin)s,
            %(normalized_district)s, %(normalized_state)s, %(normalized_city)s, %(normalized_address)s, %(address_key)s,
            %(entity_type)s, %(sector)s, %(confidence)s, %(source_flags)s, %(feature_payload)s, %(normalizer_version)s, %(name_embedding)s
        )
        ON CONFLICT (raw_record_id) DO UPDATE SET
            record_hash = EXCLUDED.record_hash,
            canonical_name = EXCLUDED.canonical_name,
            canonical_name_key = EXCLUDED.canonical_name_key,
            name_tokens = EXCLUDED.name_tokens,
            phonetic_key = EXCLUDED.phonetic_key,
            name_bucket = EXCLUDED.name_bucket,
            normalized_pan = EXCLUDED.normalized_pan,
            normalized_gstin = EXCLUDED.normalized_gstin,
            normalized_pin = EXCLUDED.normalized_pin,
            normalized_district = EXCLUDED.normalized_district,
            normalized_state = EXCLUDED.normalized_state,
            normalized_city = EXCLUDED.normalized_city,
            normalized_address = EXCLUDED.normalized_address,
            address_key = EXCLUDED.address_key,
            entity_type = EXCLUDED.entity_type,
            sector = EXCLUDED.sector,
            confidence = EXCLUDED.confidence,
            source_flags = EXCLUDED.source_flags,
            feature_payload = EXCLUDED.feature_payload,
            normalizer_version = EXCLUDED.normalizer_version,
            name_embedding = EXCLUDED.name_embedding,
            updated_at = NOW()
        RETURNING *
        """,
        {
            **record,
            "name_tokens": record.get("name_tokens") or [],
            "source_flags": _json(record.get("source_flags") or {}),
            "feature_payload": _json(record.get("feature_payload") or {}),
            "name_embedding": record.get("name_embedding"),
        },
    )
    return row or {}


def insert_normalized_records(records: list[dict]) -> list[dict]:
    return [insert_normalized_record(record) for record in records]


def get_raw_record(raw_record_id: str) -> dict | None:
    return execute_one("SELECT * FROM raw_records WHERE raw_record_id = %s", (raw_record_id,))


def get_normalized_record(normalized_record_id: str) -> dict | None:
    return execute_one("SELECT * FROM normalized_records WHERE normalized_record_id = %s", (normalized_record_id,))


def get_records_for_blocking(pin_code: str | None = None, limit: int = 100000) -> list[dict]:
    if pin_code:
        return execute(
            """
            SELECT nr.*, rr.business_name, rr.trade_name, rr.legal_name, rr.raw_payload, rr.department_code,
                   rr.pan, rr.gstin, rr.pin_code, rr.district, rr.state, rr.city, rr.address_full,
                   rr.source_status, rr.source_category
            FROM normalized_records nr
            JOIN raw_records rr ON rr.raw_record_id = nr.raw_record_id
            WHERE nr.normalized_pin = %s
            ORDER BY nr.created_at DESC
            LIMIT %s
            """,
            (pin_code, limit),
        )
    return execute(
        """
        SELECT nr.*, rr.business_name, rr.trade_name, rr.legal_name, rr.raw_payload, rr.department_code,
               rr.pan, rr.gstin, rr.pin_code, rr.district, rr.state, rr.city, rr.address_full,
               rr.source_status, rr.source_category
        FROM normalized_records nr
        JOIN raw_records rr ON rr.raw_record_id = nr.raw_record_id
        ORDER BY nr.created_at DESC
        LIMIT %s
        """,
        (limit,),
    )


def get_unlinked_records(limit: int = 5000) -> list[dict]:
    return execute(
        """
        SELECT nr.*, rr.business_name, rr.department_code, rr.pan, rr.gstin, rr.pin_code
        FROM normalized_records nr
        JOIN raw_records rr ON rr.raw_record_id = nr.raw_record_id
        LEFT JOIN cluster_members cm ON cm.normalized_record_id = nr.normalized_record_id AND cm.is_active = TRUE
        WHERE cm.normalized_record_id IS NULL
        ORDER BY nr.created_at DESC
        LIMIT %s
        """,
        (limit,),
    )


# ---------------------------------------------------------------------------
# Matching / review / clustering
# ---------------------------------------------------------------------------

def insert_match_edge(payload: dict) -> dict:
    row = execute_one(
        """
        INSERT INTO match_edges (
            processing_run_id, left_normalized_record_id, right_normalized_record_id, block_type,
            match_tier, score, confidence, auto_action, decision_state, reason_codes, signal_weights,
            explanation, left_record_snapshot, right_record_snapshot, cluster_id, ubid_id
        )
        VALUES (
            %(processing_run_id)s, %(left_normalized_record_id)s, %(right_normalized_record_id)s, %(block_type)s,
            %(match_tier)s, %(score)s, %(confidence)s, %(auto_action)s, %(decision_state)s, %(reason_codes)s,
            %(signal_weights)s, %(explanation)s, %(left_record_snapshot)s, %(right_record_snapshot)s,
            %(cluster_id)s, %(ubid_id)s
        )
        ON CONFLICT (left_normalized_record_id, right_normalized_record_id) DO UPDATE SET
            processing_run_id = EXCLUDED.processing_run_id,
            block_type = EXCLUDED.block_type,
            match_tier = EXCLUDED.match_tier,
            score = EXCLUDED.score,
            confidence = EXCLUDED.confidence,
            auto_action = EXCLUDED.auto_action,
            decision_state = EXCLUDED.decision_state,
            reason_codes = EXCLUDED.reason_codes,
            signal_weights = EXCLUDED.signal_weights,
            explanation = EXCLUDED.explanation,
            left_record_snapshot = EXCLUDED.left_record_snapshot,
            right_record_snapshot = EXCLUDED.right_record_snapshot,
            cluster_id = COALESCE(EXCLUDED.cluster_id, match_edges.cluster_id),
            ubid_id = COALESCE(EXCLUDED.ubid_id, match_edges.ubid_id),
            updated_at = NOW()
        RETURNING *
        """,
        {
            **payload,
            "reason_codes": _json(payload.get("reason_codes") or {}),
            "signal_weights": _json(payload.get("signal_weights") or {}),
            "explanation": _json(payload.get("explanation") or {}),
            "left_record_snapshot": _json(payload.get("left_record_snapshot") or {}),
            "right_record_snapshot": _json(payload.get("right_record_snapshot") or {}),
        },
    )
    return row or {}


def enqueue_review(match_id: str) -> dict:
    row = execute_one(
        """
        INSERT INTO review_cases (
            match_edge_id, processing_run_id, cluster_id, ubid_id, case_status, priority,
            review_reason, evidence
        )
        SELECT
            me.match_edge_id, me.processing_run_id, me.cluster_id, me.ubid_id, 'OPEN',
            CASE WHEN me.confidence >= 70 THEN 3 ELSE 5 END,
            me.explanation->>'verdict',
            me.explanation
        FROM match_edges me
        WHERE me.match_edge_id = %s
        ON CONFLICT (match_edge_id) DO UPDATE SET
            case_status = 'OPEN',
            last_updated_at = NOW(),
            reopened_count = review_cases.reopened_count + 1
        RETURNING *
        """,
        (match_id,),
    )
    if row:
        execute(
            "UPDATE match_edges SET decision_state = 'IN_REVIEW' WHERE match_edge_id = %s",
            (match_id,),
        )
    return row or {}


def get_pending_matches(threshold: float = 0.65, limit: int = 50) -> list[dict]:
    return execute(
        """
        SELECT
            me.match_edge_id AS id,
            rc.review_case_id,
            me.match_edge_id,
            me.score / 100.0 AS confidence,
            me.score,
            me.match_tier,
            me.block_type,
            me.decision_state,
            me.reason_codes,
            me.signal_weights,
            me.explanation,
            left_rec.normalized_record_id AS record_a_id,
            right_rec.normalized_record_id AS record_b_id,
            left_rec.canonical_name AS name_a,
            left_rec.normalized_pan AS pan_a,
            left_rec.normalized_gstin AS gstin_a,
            left_rec.normalized_pin AS pin_a,
            left_rec.normalized_address AS address_a,
            left_rec.sector AS sector_a,
            rr_left.source_status AS status_a,
            left_rec.normalized_district AS district_a,
            right_rec.canonical_name AS name_b,
            right_rec.normalized_pan AS pan_b,
            right_rec.normalized_gstin AS gstin_b,
            right_rec.normalized_pin AS pin_b,
            right_rec.normalized_address AS address_b,
            right_rec.sector AS sector_b,
            rr_right.source_status AS status_b,
            right_rec.normalized_district AS district_b
        FROM review_cases rc
        JOIN match_edges me ON me.match_edge_id = rc.match_edge_id
        JOIN normalized_records left_rec ON left_rec.normalized_record_id = me.left_normalized_record_id
        JOIN normalized_records right_rec ON right_rec.normalized_record_id = me.right_normalized_record_id
        JOIN raw_records rr_left ON rr_left.raw_record_id = left_rec.raw_record_id
        JOIN raw_records rr_right ON rr_right.raw_record_id = right_rec.raw_record_id
        WHERE rc.case_status IN ('OPEN', 'IN_REVIEW')
          AND me.decision_state IN ('PENDING', 'IN_REVIEW')
          AND me.score / 100.0 >= %s
        ORDER BY me.score DESC, rc.priority ASC, rc.opened_at ASC
        LIMIT %s
        """,
        (threshold, limit),
    )


def update_match_decision(match_id: str, decision: str, reviewer: str, justification: str, review_case_id: str | None = None) -> None:
    decision_upper = decision.upper()
    mapping = {
        "MERGED": ("APPROVED", "APPROVED"),
        "SPLIT": ("REJECTED", "REJECTED"),
        "REJECT": ("REJECTED", "REJECTED"),
        "APPROVE": ("APPROVED", "APPROVED"),
        "ESCALATE": ("ESCALATED", "ESCALATED"),
    }
    state, case_status = mapping.get(decision_upper, ("ESCALATED", "ESCALATED"))
    action_type = {
        "MERGED": "APPROVE",
        "APPROVE": "APPROVE",
        "SPLIT": "REJECT",
        "REJECT": "REJECT",
        "ESCALATE": "ESCALATE",
    }.get(decision_upper, "ESCALATE")
    execute(
        """
        UPDATE match_edges
        SET decision_state = %s,
            resolved_by = %s,
            resolved_at = NOW(),
            updated_at = NOW()
        WHERE match_edge_id = %s
        """,
        (state, reviewer, match_id),
    )
    case = execute_one("SELECT review_case_id FROM review_cases WHERE match_edge_id = %s", (match_id,))
    if case:
        execute(
            """
            INSERT INTO review_actions (
                review_case_id, match_edge_id, actor_id, actor_name, actor_role, action_type,
                decision_value, note, rationale, before_state, after_state
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                case["review_case_id"],
                match_id,
                reviewer,
                reviewer,
                "reviewer",
                action_type,
                decision_upper,
                justification,
                _json({"decision": decision}),
                _json({"decision_state": "PENDING"}),
                _json({"decision_state": state}),
            ),
        )
        execute(
            """
            UPDATE review_cases
            SET case_status = %s,
                review_summary = %s,
                closed_at = CASE WHEN %s IN ('APPROVED', 'REJECTED', 'ESCALATED') THEN NOW() ELSE closed_at END
            WHERE review_case_id = %s
            """,
            (case_status, justification, case_status, case["review_case_id"]),
        )


def create_cluster(payload: dict) -> dict:
    row = execute_one(
        """
        INSERT INTO entity_clusters (
            cluster_code, cluster_hash, cluster_state, canonical_name, canonical_name_key,
            district, state, pin_code, canonical_pan, canonical_gstin, member_count,
            record_count, confidence_score, created_run_id, current_ubid_id, summary
        )
        VALUES (
            %(cluster_code)s, %(cluster_hash)s, %(cluster_state)s, %(canonical_name)s, %(canonical_name_key)s,
            %(district)s, %(state)s, %(pin_code)s, %(canonical_pan)s, %(canonical_gstin)s, %(member_count)s,
            %(record_count)s, %(confidence_score)s, %(created_run_id)s, %(current_ubid_id)s, %(summary)s
        )
        ON CONFLICT (cluster_hash) DO UPDATE SET
            canonical_name = EXCLUDED.canonical_name,
            canonical_name_key = EXCLUDED.canonical_name_key,
            district = EXCLUDED.district,
            state = EXCLUDED.state,
            pin_code = EXCLUDED.pin_code,
            canonical_pan = EXCLUDED.canonical_pan,
            canonical_gstin = EXCLUDED.canonical_gstin,
            member_count = EXCLUDED.member_count,
            record_count = EXCLUDED.record_count,
            confidence_score = EXCLUDED.confidence_score,
            current_ubid_id = COALESCE(EXCLUDED.current_ubid_id, entity_clusters.current_ubid_id),
            summary = EXCLUDED.summary,
            updated_at = NOW()
        RETURNING *
        """,
        {**payload, "summary": _json(payload.get("summary") or {})},
    )
    return row or {}


def create_cluster_member(payload: dict) -> dict:
    row = execute_one(
        """
        INSERT INTO cluster_members (
            cluster_id, normalized_record_id, ubid_id, match_edge_id, member_role,
            membership_confidence, join_reason, is_canonical, is_active, joined_at, left_at
        )
        VALUES (
            %(cluster_id)s, %(normalized_record_id)s, %(ubid_id)s, %(match_edge_id)s, %(member_role)s,
            %(membership_confidence)s, %(join_reason)s, %(is_canonical)s, %(is_active)s, %(joined_at)s, %(left_at)s
        )
        ON CONFLICT (normalized_record_id) DO UPDATE SET
            cluster_id = EXCLUDED.cluster_id,
            ubid_id = COALESCE(EXCLUDED.ubid_id, cluster_members.ubid_id),
            match_edge_id = COALESCE(EXCLUDED.match_edge_id, cluster_members.match_edge_id),
            member_role = EXCLUDED.member_role,
            membership_confidence = EXCLUDED.membership_confidence,
            join_reason = EXCLUDED.join_reason,
            is_canonical = EXCLUDED.is_canonical,
            is_active = EXCLUDED.is_active,
            left_at = EXCLUDED.left_at
        RETURNING *
        """,
        {**payload, "join_reason": _json(payload.get("join_reason") or {})},
    )
    return row or {}


def create_ubid(payload: dict) -> dict:
    row = execute_one(
        """
        INSERT INTO ubids (
            ubid_code, cluster_id, canonical_name, canonical_name_key, legal_name, trade_name,
            normalized_pan, normalized_gstin, normalized_pin, district, state, address_normalized,
            first_seen_at, last_seen_at, record_count, source_count, status_source, summary, created_run_id
        )
        VALUES (
            %(ubid_code)s, %(cluster_id)s, %(canonical_name)s, %(canonical_name_key)s, %(legal_name)s, %(trade_name)s,
            %(normalized_pan)s, %(normalized_gstin)s, %(normalized_pin)s, %(district)s, %(state)s, %(address_normalized)s,
            %(first_seen_at)s, %(last_seen_at)s, %(record_count)s, %(source_count)s, %(status_source)s, %(summary)s, %(created_run_id)s
        )
        ON CONFLICT (ubid_code) DO UPDATE SET
            cluster_id = COALESCE(EXCLUDED.cluster_id, ubids.cluster_id),
            canonical_name = EXCLUDED.canonical_name,
            canonical_name_key = EXCLUDED.canonical_name_key,
            legal_name = EXCLUDED.legal_name,
            trade_name = EXCLUDED.trade_name,
            normalized_pan = EXCLUDED.normalized_pan,
            normalized_gstin = EXCLUDED.normalized_gstin,
            normalized_pin = EXCLUDED.normalized_pin,
            district = EXCLUDED.district,
            state = EXCLUDED.state,
            address_normalized = EXCLUDED.address_normalized,
            first_seen_at = LEAST(COALESCE(ubids.first_seen_at, EXCLUDED.first_seen_at), EXCLUDED.first_seen_at),
            last_seen_at = GREATEST(COALESCE(ubids.last_seen_at, EXCLUDED.last_seen_at), EXCLUDED.last_seen_at),
            record_count = EXCLUDED.record_count,
            source_count = EXCLUDED.source_count,
            status_source = EXCLUDED.status_source,
            summary = EXCLUDED.summary,
            updated_at = NOW()
        RETURNING *
        """,
        {**payload, "summary": _json(payload.get("summary") or {})},
    )
    return row or {}


def link_record_to_ubid(ubid_id: str, normalized_record_id: str, confidence: float, linked_by: str = "system", match_edge_id: str | None = None, cluster_id: str | None = None) -> dict:
    if cluster_id is None:
        cluster = execute_one("SELECT cluster_id FROM ubids WHERE ubid_id::text = %s", (ubid_id,))
        cluster_id = cluster.get("cluster_id") if cluster else None
    if cluster_id is None:
        cluster = create_cluster(
            {
                "cluster_code": f"CL-{uuid.uuid4().hex[:10].upper()}",
                "cluster_hash": sha256(f"{ubid_id}:{normalized_record_id}".encode("utf-8")).hexdigest(),
                "cluster_state": "OPEN",
                "canonical_name": "Manual Cluster",
                "canonical_name_key": "manual cluster",
                "district": None,
                "state": None,
                "pin_code": None,
                "canonical_pan": None,
                "canonical_gstin": None,
                "member_count": 0,
                "record_count": 0,
                "confidence_score": 0,
                "created_run_id": None,
                "summary": {},
            }
        )
        cluster_id = cluster.get("cluster_id")
    return create_cluster_member(
        {
            "cluster_id": cluster_id,
            "normalized_record_id": normalized_record_id,
            "ubid_id": ubid_id,
            "match_edge_id": match_edge_id,
            "member_role": "MEMBER",
            "membership_confidence": round(float(confidence) * 100, 2),
            "join_reason": {"linked_by": linked_by, "confidence": confidence},
            "is_canonical": False,
            "is_active": True,
            "joined_at": datetime.now(timezone.utc),
            "left_at": None,
        }
    )


def update_entity_vitality(ubid: str, status: str, score: float, pulse: int, record_override: bool = True) -> None:
    execute(
        """
        UPDATE ubids
        SET summary = jsonb_set(
                jsonb_set(summary, '{manual_status}', to_jsonb(%s::text), true),
                '{manual_score}', to_jsonb(%s::numeric), true
            ),
            updated_at = NOW()
        WHERE ubid_id::text = %s
        """,
        (status, score, ubid),
    )
    if record_override:
        upsert_status_event(
            {
                "ubid_id": ubid,
                "raw_record_id": None,
                "event_type": "MANUAL_OVERRIDE",
                "event_source": "ui",
                "event_date": datetime.now(timezone.utc),
                "activity_weight": 0.0,
                "derived_status": status,
                "details": {"manual_score": score, "pulse": pulse},
            }
        )


def get_entity(ubid: str) -> dict | None:
    row = execute_one(
        """
        SELECT
            u.*,
            v.current_status,
            v.latest_activity_at,
            v.pulse_score
        FROM ubids u
        LEFT JOIN v_ubid_registry v ON v.ubid_id = u.ubid_id
        WHERE u.ubid_id::text = %s OR u.ubid_code = %s
        """,
        (ubid, ubid),
    )
    if not row:
        return None
    row["status"] = row.pop("current_status", None)
    row["last_activity_at"] = row.pop("latest_activity_at", None)
    row["ubid"] = str(row.get("ubid_id"))
    row["linked_records"] = row.get("linked_records", row.get("member_count", 0))
    row["total_events"] = row.get("total_events", 0)
    return row


def search_entities(query: str, pin_code: str | None = None, vitality: str | None = None, limit: int = 50) -> list[dict]:
    like = f"%{query.strip()}%" if query else None
    rows = execute(
        """
        SELECT *
        FROM v_ubid_registry
        WHERE (%s IS NULL OR canonical_name ILIKE %s OR ubid_code ILIKE %s OR COALESCE(normalized_pan, '') ILIKE %s OR COALESCE(normalized_gstin, '') ILIKE %s)
          AND (%s IS NULL OR normalized_pin = %s)
          AND (%s = 'ALL' OR current_status = %s)
        ORDER BY updated_at DESC
        LIMIT %s
        """,
        (like, like, like, like, like, pin_code, pin_code, vitality or "ALL", vitality or "ALL", limit),
    )
    for row in rows:
        row["ubid"] = str(row.get("ubid_id"))
        row["status"] = row.get("current_status")
        row["linked_records"] = row.get("linked_records", row.get("member_count", 0))
        row["total_events"] = row.get("total_events", 0)
        row["latest_event_date"] = row.get("latest_activity_at")
    return rows


def get_entity_records(ubid: str) -> list[dict]:
    return execute(
        """
        SELECT
            cm.membership_confidence AS link_confidence,
            cm.joined_at AS linked_at,
            cm.member_role AS linked_role,
            cm.is_canonical,
            rr.raw_record_id,
            nr.normalized_record_id,
            nr.canonical_name,
            nr.normalized_pan,
            nr.normalized_gstin,
            nr.normalized_pin,
            nr.normalized_state,
            nr.normalized_district,
            nr.normalized_city,
            nr.normalized_address,
            nr.sector,
            rr.business_name,
            rr.department_code,
            rr.pan,
            rr.gstin,
            rr.pin_code,
            rr.source_status AS status_raw,
            rr.source_category,
            rr.activity_date,
            rr.registration_date,
            rr.created_at AS raw_created_at
        FROM cluster_members cm
        JOIN normalized_records nr ON nr.normalized_record_id = cm.normalized_record_id
        JOIN raw_records rr ON rr.raw_record_id = nr.raw_record_id
        WHERE (
            cm.ubid_id::text = %s
            OR EXISTS (
            SELECT 1 FROM ubids u WHERE u.ubid_id::text = %s AND u.cluster_id = cm.cluster_id
            )
        )
        ORDER BY cm.is_canonical DESC, rr.department_code, rr.created_at DESC
        """,
        (ubid, ubid),
    )


def get_entity_events(ubid: str) -> list[dict]:
    return execute(
        """
        SELECT *
        FROM status_events
        WHERE ubid_id::text = %s
        ORDER BY event_date DESC
        """,
        (ubid,),
    )


def get_vitality_signals(ubid: str) -> dict:
    row = execute_one(
        """
        SELECT
            COUNT(*) AS total_events,
            COUNT(*) FILTER (WHERE event_date > NOW() - INTERVAL '180 days') AS events_6m,
            COUNT(*) FILTER (WHERE event_date > NOW() - INTERVAL '365 days') AS events_12m,
            COUNT(*) FILTER (WHERE event_date > NOW() - INTERVAL '540 days') AS events_18m,
            COUNT(*) FILTER (WHERE event_type = 'RENEWAL') AS renewals,
            COUNT(*) FILTER (WHERE event_type = 'INSPECTION') AS inspections,
            COUNT(*) FILTER (WHERE event_type = 'FILING') AS filings,
            COUNT(*) FILTER (WHERE event_type = 'UTILITY') AS utility_events,
            COUNT(*) FILTER (WHERE event_type = 'SHUTDOWN') AS shutdowns,
            MAX(event_date) AS last_event,
            MIN(event_date) AS first_event,
            AVG(activity_weight) AS avg_signal
        FROM status_events
        WHERE ubid_id::text = %s
        """,
        (ubid,),
    )
    return row or {}


def upsert_status_event(payload: dict) -> dict:
    existing = execute_one(
        """
        SELECT status_event_id
        FROM status_events
        WHERE ubid_id::text = %s
          AND COALESCE(raw_record_id::text, '') = COALESCE(%s, '')
          AND event_type = %s
          AND event_date = %s
        LIMIT 1
        """,
        (
            str(payload.get("ubid_id")),
            str(payload.get("raw_record_id")) if payload.get("raw_record_id") else "",
            payload.get("event_type"),
            payload.get("event_date"),
        ),
    )
    if existing:
        return existing
    row = execute_one(
        """
        INSERT INTO status_events (
            ubid_id, raw_record_id, event_type, event_source, event_date, activity_weight, derived_status, details
        )
        VALUES (%(ubid_id)s, %(raw_record_id)s, %(event_type)s, %(event_source)s, %(event_date)s, %(activity_weight)s, %(derived_status)s, %(details)s)
        RETURNING *
        """,
        {**payload, "details": _json(payload.get("details") or {})},
    )
    return row or {}


def count_raw_records() -> int:
    return int((execute_one("SELECT COUNT(*) AS n FROM raw_records") or {}).get("n", 0))


def count_entities() -> int:
    return int((execute_one("SELECT COUNT(*) AS n FROM ubids") or {}).get("n", 0))


def count_activity_events() -> int:
    return int((execute_one("SELECT COUNT(*) AS n FROM status_events") or {}).get("n", 0))


def count_audit_log() -> int:
    return int((execute_one("SELECT COUNT(*) AS n FROM audit_logs") or {}).get("n", 0))


def count_pending_reviews() -> int:
    return int((execute_one("SELECT COUNT(*) AS n FROM review_cases WHERE case_status IN ('OPEN','IN_REVIEW')") or {}).get("n", 0))


def get_dashboard_stats() -> dict:
    base = execute_one("SELECT * FROM v_dashboard_summary") or {}
    statuses = execute_one(
        """
        SELECT
            COUNT(*) FILTER (WHERE current_status = 'ACTIVE') AS active_count,
            COUNT(*) FILTER (WHERE current_status = 'DORMANT') AS dormant_count,
            COUNT(*) FILTER (WHERE current_status = 'CLOSED') AS closed_count,
            COUNT(*) FILTER (WHERE current_status NOT IN ('ACTIVE', 'DORMANT', 'CLOSED')) AS unknown_count,
            ROUND(AVG(record_count)::numeric, 2) AS avg_record_count,
            COUNT(*) FILTER (WHERE record_count > 1) AS multi_dept_entities
        FROM v_ubid_registry
        """
    ) or {}
    merged = {
        **base,
        **statuses,
        "pending_reviews": count_pending_reviews(),
        "total_raw_records": count_raw_records(),
        "total_audit_events": count_audit_log(),
    }
    merged["total_entities"] = merged.get("total_ubids", 0)
    merged["unknown_count"] = merged.get("unknown_count", 0)
    return merged


def get_entities_by_sector(limit: int = 20) -> list[dict]:
    return execute(
        """
        SELECT
            COALESCE(sector, 'Unknown') AS sector,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE current_status = 'ACTIVE') AS active,
            COUNT(*) FILTER (WHERE current_status = 'DORMANT') AS dormant,
            COUNT(*) FILTER (WHERE current_status = 'CLOSED') AS closed
        FROM v_ubid_registry
        GROUP BY COALESCE(sector, 'Unknown')
        ORDER BY total DESC
        LIMIT %s
        """,
        (limit,),
    )


def get_vitality_by_pin() -> list[dict]:
    return execute(
        """
        SELECT
            COALESCE(normalized_pin, 'Unknown') AS pin_code,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE current_status = 'ACTIVE') AS active,
            COUNT(*) FILTER (WHERE current_status = 'DORMANT') AS dormant,
            ROUND(AVG(COALESCE(pulse_score, 0))::numeric, 1) AS avg_pulse
        FROM v_ubid_registry
        GROUP BY COALESCE(normalized_pin, 'Unknown')
        ORDER BY total DESC
        """
    )


def get_active_entity_ids(limit: int = 5000) -> list[dict]:
    return execute(
        """
        SELECT ubid_id AS ubid
        FROM ubids
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )


def get_all_match_edges(status_filter: list[str] | None = None) -> list[dict]:
    statuses = status_filter or ["AUTO_MERGED", "IN_REVIEW", "APPROVED"]
    return execute(
        """
        SELECT
            me.match_edge_id AS id,
            me.left_normalized_record_id AS record_a_id,
            me.right_normalized_record_id AS record_b_id,
            me.score / 100.0 AS confidence,
            me.decision_state AS match_status,
            left_rec.canonical_name AS name_a,
            left_raw.department_code AS dept_a,
            left_rec.normalized_pan AS pan_a,
            left_rec.normalized_gstin AS gstin_a,
            left_rec.normalized_pin AS pin_a,
            left_rec.normalized_address AS address_a,
            left_rec.sector AS sector_a,
            right_rec.canonical_name AS name_b,
            right_raw.department_code AS dept_b,
            right_rec.normalized_pan AS pan_b,
            right_rec.normalized_gstin AS gstin_b,
            right_rec.normalized_pin AS pin_b,
            right_rec.normalized_address AS address_b,
            right_rec.sector AS sector_b
        FROM match_edges me
        JOIN normalized_records left_rec ON left_rec.normalized_record_id = me.left_normalized_record_id
        JOIN normalized_records right_rec ON right_rec.normalized_record_id = me.right_normalized_record_id
        JOIN raw_records left_raw ON left_raw.raw_record_id = left_rec.raw_record_id
        JOIN raw_records right_raw ON right_raw.raw_record_id = right_rec.raw_record_id
        WHERE me.decision_state = ANY(%s)
        ORDER BY me.score DESC
        LIMIT 500
        """,
        (statuses,),
    )


def get_match_stats() -> dict:
    row = execute_one(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE decision_state = 'AUTO_MERGED') AS auto_linked,
            COUNT(*) FILTER (WHERE decision_state = 'IN_REVIEW') AS in_review,
            COUNT(*) FILTER (WHERE decision_state = 'APPROVED') AS merged,
            COUNT(*) FILTER (WHERE decision_state IN ('REJECTED', 'REVERSED')) AS rejected,
            ROUND(AVG(score / 100.0)::numeric, 3) AS avg_conf
        FROM match_edges
        """
    )
    return row or {}


def get_graph_clusters_cte(seed_record_id: str) -> list[dict]:
    return execute(
        """
        WITH RECURSIVE graph AS (
            SELECT left_normalized_record_id AS node_id, right_normalized_record_id AS neighbor_id
            FROM match_edges
            WHERE left_normalized_record_id::text = %s OR right_normalized_record_id::text = %s
            UNION
            SELECT me.left_normalized_record_id, me.right_normalized_record_id
            FROM match_edges me
            JOIN graph g ON g.neighbor_id = me.left_normalized_record_id OR g.neighbor_id = me.right_normalized_record_id
        )
        SELECT * FROM graph
        """,
        (seed_record_id, seed_record_id),
    )


def get_review_cases(limit: int = 50) -> list[dict]:
    return execute(
        """
        SELECT *
        FROM v_review_queue
        ORDER BY priority ASC, opened_at DESC
        LIMIT %s
        """,
        (limit,),
    )


def get_review_case(review_case_id: str) -> dict | None:
    return execute_one("SELECT * FROM review_cases WHERE review_case_id = %s", (review_case_id,))


def get_audit_trail(entity_ubid: str | None = None, limit: int = 100) -> list[dict]:
    if entity_ubid:
        return execute(
            """
            SELECT
                audit_log_id AS id,
                created_at,
                event_type,
                actor_id AS actor,
                action,
                severity,
                entity_type,
                entity_id AS entity_ubid,
                before_state,
                after_state,
                metadata,
                correlation_id
            FROM audit_logs
            WHERE entity_type = 'UBID' AND entity_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (entity_ubid, limit),
        )
    return execute(
        """
        SELECT
            audit_log_id AS id,
            created_at,
            event_type,
            actor_id AS actor,
            action,
            severity,
            entity_type,
            entity_id AS entity_ubid,
            before_state,
            after_state,
            metadata,
            correlation_id
        FROM audit_logs
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )


def log_audit(
    event_type: str,
    action: str,
    actor: str = "system",
    entity_ubid: str | None = None,
    match_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    confidence: float | None = None,
    justification: str | None = None,
    entity_type: str = "SYSTEM",
    severity: str = "INFO",
    run_id: str | None = None,
) -> None:
    resolved_entity_type = entity_type
    if entity_ubid and entity_type == "SYSTEM":
        resolved_entity_type = "UBID"
    elif match_id and entity_type == "SYSTEM":
        resolved_entity_type = "MATCH"
    execute(
        """
        INSERT INTO audit_logs (
            run_id, actor_id, actor_role, event_type, entity_type, entity_id, action, severity,
            before_state, after_state, metadata, correlation_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            run_id,
            actor,
            actor,
            event_type,
            resolved_entity_type,
            entity_ubid or match_id or "system",
            action,
            severity,
            _json(before) if before is not None else None,
            _json(after) if after is not None else None,
            _json({"confidence": confidence, "justification": justification}),
            None,
        ),
    )


def run_structured_query(params: dict) -> list[dict]:
    sql = """
        SELECT *
        FROM v_ubid_registry
        WHERE (%(vitality)s IS NULL OR current_status = %(vitality)s)
          AND (%(pin_code)s IS NULL OR normalized_pin = %(pin_code)s)
          AND (%(dept)s IS NULL OR COALESCE(summary->'departments', '[]'::jsonb) @> to_jsonb(ARRAY[%(dept)s]))
          AND (%(sector)s IS NULL OR canonical_name ILIKE %(sector_like)s OR COALESCE(summary->>'sector', '') ILIKE %(sector_like)s)
    """
    values = {
        "vitality": params.get("vitality"),
        "pin_code": params.get("pin_code"),
        "dept": params.get("dept"),
        "sector": params.get("sector"),
        "sector_like": f"%{params.get('sector')}%" if params.get("sector") else None,
    }
    rows = execute(sql + " ORDER BY COALESCE(last_seen_at, created_at) DESC LIMIT %(limit)s", {**values, "limit": params.get("limit", 50)})
    if params.get("no_inspection_months"):
        months = int(params["no_inspection_months"])
        cutoff = datetime.now(timezone.utc) - timedelta(days=30 * months)
        filtered = []
        for row in rows:
            latest_inspection = execute_one(
                """
                SELECT MAX(event_date) AS latest
                FROM status_events
                WHERE ubid_id::text = %s AND event_type = 'INSPECTION'
                """,
                (row["ubid_id"],),
            )
            latest = latest_inspection and latest_inspection.get("latest")
            if not latest or latest <= cutoff:
                filtered.append(row)
        rows = filtered
    return rows[: min(int(params.get("limit", 50)), 500)]


def get_learning_labels() -> list[dict]:
    return execute(
        """
        SELECT
            me.match_edge_id AS id,
            me.score / 100.0 AS confidence,
            me.decision_state AS match_status,
            me.reason_codes,
            me.signal_weights,
            me.explanation,
            CASE WHEN me.decision_state = 'APPROVED' THEN 1 ELSE 0 END AS reviewer_label,
            me.resolved_by AS reviewed_by,
            me.resolved_at AS reviewed_at
        FROM match_edges me
        WHERE me.decision_state IN ('APPROVED', 'REJECTED')
        ORDER BY me.resolved_at DESC NULLS LAST
        """
    )


def get_threshold_stats() -> dict:
    return execute_one(
        """
        SELECT
            COALESCE(AVG(score / 100.0) FILTER (WHERE decision_state = 'APPROVED'), 0) AS avg_merge_confidence,
            COALESCE(AVG(score / 100.0) FILTER (WHERE decision_state IN ('REJECTED', 'REVERSED')), 0) AS avg_reject_confidence,
            COUNT(*) FILTER (WHERE decision_state = 'APPROVED') AS total_merges,
            COUNT(*) FILTER (WHERE decision_state IN ('REJECTED', 'REVERSED')) AS total_rejects,
            COALESCE(MIN(score / 100.0) FILTER (WHERE decision_state = 'APPROVED'), 0) AS min_merge_confidence,
            COALESCE(MAX(score / 100.0) FILTER (WHERE decision_state IN ('REJECTED', 'REVERSED')), 0) AS max_reject_confidence
        FROM match_edges
        """
    ) or {}


# ---------------------------------------------------------------------------
# Compatibility helpers for legacy UI
# ---------------------------------------------------------------------------

def create_entity(entity: dict) -> str:
    ubid_code = entity.get("ubid") or f"UBID-{uuid.uuid4().hex[:12].upper()}"
    cluster = create_cluster(
        {
            "cluster_code": f"CL-{uuid.uuid4().hex[:10].upper()}",
            "cluster_hash": sha256(f"{ubid_code}:{entity.get('canonical_name','')}".encode("utf-8")).hexdigest(),
            "cluster_state": "OPEN",
            "canonical_name": entity.get("canonical_name", ""),
            "canonical_name_key": (entity.get("canonical_name", "") or "").lower(),
            "district": entity.get("district"),
            "state": entity.get("state"),
            "pin_code": entity.get("pin_code"),
            "canonical_pan": entity.get("pan"),
            "canonical_gstin": entity.get("gstin"),
            "member_count": entity.get("record_count", 1),
            "record_count": entity.get("record_count", 1),
            "confidence_score": 100.0,
            "created_run_id": entity.get("created_run_id"),
            "summary": {"sector": entity.get("sector"), "departments": entity.get("departments") or []},
        }
    )
    row = create_ubid(
        {
            "ubid_code": ubid_code,
            "cluster_id": cluster.get("cluster_id"),
            "canonical_name": entity.get("canonical_name", ""),
            "canonical_name_key": (entity.get("canonical_name", "") or "").lower(),
            "legal_name": entity.get("legal_name"),
            "trade_name": entity.get("trade_name"),
            "normalized_pan": entity.get("pan"),
            "normalized_gstin": entity.get("gstin"),
            "normalized_pin": entity.get("pin_code"),
            "district": entity.get("district"),
            "state": entity.get("state"),
            "address_normalized": entity.get("address"),
            "first_seen_at": datetime.now(timezone.utc),
            "last_seen_at": datetime.now(timezone.utc),
            "record_count": entity.get("record_count", 1),
            "source_count": len(entity.get("departments") or []),
            "status_source": "derived_view",
            "summary": {"sector": entity.get("sector"), "departments": entity.get("departments") or []},
            "created_run_id": entity.get("created_run_id"),
        }
    )
    execute("UPDATE entity_clusters SET current_ubid_id = %s WHERE cluster_id = %s", (row.get("ubid_id"), cluster.get("cluster_id")))
    return str(row.get("ubid_id") or ubid_code)


def link_record_to_entity(ubid: str, record_id: str, confidence: float, linked_by: str = "system") -> None:
    link_record_to_ubid(ubid, record_id, confidence, linked_by)
