from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import itertools
import re
from typing import Any
import uuid

import jellyfish
from loguru import logger
from rapidfuzz import fuzz
from unidecode import unidecode

from db import queries
from engine.explainability import generate_explanation

AUTO_MERGE_THRESHOLD = float(__import__("os").getenv("AUTO_MERGE_THRESHOLD", "85"))
REVIEW_THRESHOLD = float(__import__("os").getenv("REVIEW_THRESHOLD", "50"))


def _normalize(text: str) -> str:
    text = unidecode(text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _token_bucket(name: str) -> str:
    tokens = _normalize(name).split()
    if not tokens:
        return "unknown"
    head = tokens[0][:3]
    tail = tokens[-1][:3] if len(tokens) > 1 else tokens[0][:3]
    return f"{head}:{tail}"


def _phonetic(name: str) -> str:
    try:
        return jellyfish.metaphone(_normalize(name))
    except Exception:
        return _normalize(name)[:8]


def _hash_embedding_score(a: str, b: str) -> float:
    ta = set(_normalize(a).split())
    tb = set(_normalize(b).split())
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return round(inter / max(union, 1), 4)


@dataclass
class MatchSignals:
    pan_match: bool = False
    gstin_match: bool = False
    name_phonetic_score: float = 0.0
    name_fuzzy_score: float = 0.0
    embedding_score: float = 0.0
    pin_match: bool = False
    address_score: float = 0.0
    graph_boost: float = 0.0


def normalize_name(name: str) -> str:
    return _normalize(name)


def metaphone_key(name: str) -> str:
    return _phonetic(name)


def fuzzy_ratio(a: str, b: str) -> float:
    return round(fuzz.token_sort_ratio(_normalize(a), _normalize(b)) / 100.0, 4)


def address_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return round(fuzz.partial_ratio(_normalize(a), _normalize(b)) / 100.0, 4)


def build_blocks(records: list[dict]) -> dict[str, list[dict]]:
    blocks: dict[str, list[dict]] = {}
    for rec in records:
        name = rec.get("canonical_name") or rec.get("business_name") or ""
        pin = str(rec.get("normalized_pin") or rec.get("pin_code") or "").strip()
        pan = str(rec.get("normalized_pan") or rec.get("pan") or "").strip().upper()
        gstin = str(rec.get("normalized_gstin") or rec.get("gstin") or "").strip().upper()
        district = str(rec.get("normalized_district") or rec.get("district") or "").strip().lower()
        bucket = _token_bucket(name)
        phonetic = _phonetic(name)
        keys = set()
        if pan and len(pan) == 10:
            keys.add(f"PAN:{pan}")
        if gstin and len(gstin) == 15:
            keys.add(f"GSTIN:{gstin}")
        if pin:
            keys.add(f"PIN:{pin}:{bucket}")
            keys.add(f"PINP:{pin}:{phonetic}")
        if district:
            keys.add(f"DIST:{district}:{bucket}")
        for key in keys:
            blocks.setdefault(key, []).append(rec)
    return {k: v for k, v in blocks.items() if len(v) > 1}


def get_candidate_pairs(records: list[dict]) -> list[tuple[dict, dict]]:
    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[dict, dict]] = []
    for block_records in build_blocks(records).values():
        for left, right in itertools.combinations(block_records, 2):
            a = str(left["normalized_record_id"])
            b = str(right["normalized_record_id"])
            key = (a, b) if a < b else (b, a)
            if key not in seen:
                seen.add(key)
                pairs.append((left, right))
    logger.info("Blocking produced {} candidate pairs from {} records", len(pairs), len(records))
    return pairs


def score_pair(a: dict, b: dict) -> MatchSignals:
    name_a = a.get("canonical_name") or a.get("business_name") or ""
    name_b = b.get("canonical_name") or b.get("business_name") or ""
    pan_a = str(a.get("normalized_pan") or a.get("pan") or "").strip().upper()
    pan_b = str(b.get("normalized_pan") or b.get("pan") or "").strip().upper()
    gst_a = str(a.get("normalized_gstin") or a.get("gstin") or "").strip().upper()
    gst_b = str(b.get("normalized_gstin") or b.get("gstin") or "").strip().upper()
    pin_a = str(a.get("normalized_pin") or a.get("pin_code") or "").strip()
    pin_b = str(b.get("normalized_pin") or b.get("pin_code") or "").strip()
    addr_a = a.get("normalized_address") or a.get("address_full") or ""
    addr_b = b.get("normalized_address") or b.get("address_full") or ""
    sig = MatchSignals()
    if pan_a and pan_b and len(pan_a) == 10:
        sig.pan_match = pan_a == pan_b
    if gst_a and gst_b and len(gst_a) == 15:
        sig.gstin_match = gst_a == gst_b
    sig.name_phonetic_score = 1.0 if _phonetic(name_a) == _phonetic(name_b) and name_a and name_b else 0.0
    sig.name_fuzzy_score = fuzzy_ratio(name_a, name_b)
    sig.embedding_score = _hash_embedding_score(name_a + " " + addr_a, name_b + " " + addr_b)
    sig.pin_match = bool(pin_a and pin_b and pin_a == pin_b)
    sig.address_score = address_similarity(addr_a, addr_b)
    return sig


def compute_confidence(sig: MatchSignals) -> float:
    if sig.pan_match or sig.gstin_match:
        score = 92.0 + (4.0 if sig.pin_match else 0.0) + (4.0 * sig.name_fuzzy_score)
        return round(min(score, 99.0), 2)
    score = (
        sig.name_phonetic_score * 15.0
        + sig.name_fuzzy_score * 45.0
        + sig.embedding_score * 15.0
        + (10.0 if sig.pin_match else 0.0)
        + sig.address_score * 15.0
        + sig.graph_boost * 10.0
    )
    return round(min(score, 91.0), 2)


def determine_status(confidence: float) -> str:
    if confidence > 85:
        return "AUTO_MERGED"
    if confidence >= 50:
        return "IN_REVIEW"
    return "REJECTED"


def _build_explanation(sig: MatchSignals, confidence: float, status: str) -> dict:
    pair = {
        "pan_match": sig.pan_match,
        "gstin_match": sig.gstin_match,
        "name_phonetic_score": sig.name_phonetic_score,
        "name_fuzzy_score": sig.name_fuzzy_score,
        "embedding_score": sig.embedding_score,
        "pin_match": sig.pin_match,
        "address_score": sig.address_score,
        "graph_boost": sig.graph_boost,
        "confidence": confidence / 100.0,
        "match_status": "AUTO_LINKED" if status == "AUTO_MERGED" else ("REVIEW" if status == "IN_REVIEW" else "REJECTED"),
    }
    return generate_explanation(pair)


def _cluster_hash(record_ids: list[str]) -> str:
    payload = "||".join(sorted(record_ids))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ubid_code() -> str:
    return f"UBID-{uuid.uuid4().hex[:12].upper()}"


def _union_find(records: list[str], edges: list[tuple[str, str]]) -> dict[str, str]:
    parent = {rid: rid for rid in records}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a, b in edges:
        union(a, b)
    return {rid: find(rid) for rid in records}


def _create_cluster_and_ubid(members: list[dict], seed_run_id: str | None) -> str:
    canonical = sorted(
        members,
        key=lambda r: (
            not bool(r.get("normalized_pan")),
            not bool(r.get("normalized_gstin")),
            r.get("canonical_name") or "",
        ),
    )[0]
    record_ids = [str(m["normalized_record_id"]) for m in members]
    cluster = queries.create_cluster(
        {
            "cluster_code": f"CL-{uuid.uuid4().hex[:10].upper()}",
            "cluster_hash": _cluster_hash(record_ids),
            "cluster_state": "OPEN",
            "canonical_name": canonical.get("canonical_name") or canonical.get("business_name") or "",
            "canonical_name_key": normalize_name(canonical.get("canonical_name") or canonical.get("business_name") or ""),
            "district": canonical.get("normalized_district") or canonical.get("district"),
            "state": canonical.get("normalized_state") or canonical.get("state"),
            "pin_code": canonical.get("normalized_pin") or canonical.get("pin_code"),
            "canonical_pan": canonical.get("normalized_pan") or canonical.get("pan"),
            "canonical_gstin": canonical.get("normalized_gstin") or canonical.get("gstin"),
            "member_count": len(members),
            "record_count": len(members),
            "confidence_score": 95.0,
            "created_run_id": seed_run_id,
            "summary": {"record_ids": record_ids},
        }
    )
    ubid = queries.create_ubid(
        {
            "ubid_code": _ubid_code(),
            "cluster_id": cluster.get("cluster_id"),
            "canonical_name": cluster.get("canonical_name"),
            "canonical_name_key": cluster.get("canonical_name_key"),
            "legal_name": canonical.get("legal_name"),
            "trade_name": canonical.get("trade_name"),
            "normalized_pan": cluster.get("canonical_pan"),
            "normalized_gstin": cluster.get("canonical_gstin"),
            "normalized_pin": cluster.get("pin_code"),
            "district": cluster.get("district"),
            "state": cluster.get("state"),
            "address_normalized": canonical.get("normalized_address") or canonical.get("address_full"),
            "first_seen_at": canonical.get("created_at") or datetime.now(timezone.utc),
            "last_seen_at": canonical.get("created_at") or datetime.now(timezone.utc),
            "record_count": len(members),
            "source_count": len({m.get("department_code") for m in members}),
            "status_source": "derived_view",
            "summary": {"sector": canonical.get("sector"), "departments": sorted({m.get("department_code") for m in members})},
            "created_run_id": seed_run_id,
        }
    )
    for member in members:
        queries.link_record_to_ubid(
            ubid.get("ubid_id"),
            member["normalized_record_id"],
            0.95,
            linked_by="system",
            cluster_id=cluster.get("cluster_id"),
        )
    queries.execute("UPDATE entity_clusters SET current_ubid_id = %s WHERE cluster_id = %s", (ubid.get("ubid_id"), cluster.get("cluster_id")))
    return str(ubid.get("ubid_id"))


def run_resolution(records: list[dict] | None = None, pin_code: str | None = None, processing_run_id: str | None = None) -> dict[str, Any]:
    if records is None:
        records = queries.get_records_for_blocking(pin_code=pin_code)
    if len(records) < 2:
        return {"total_records": len(records), "total_pairs": 0, "auto_linked": 0, "review": 0, "rejected": 0}

    pairs = get_candidate_pairs(records)
    scored: list[dict] = []
    for left, right in pairs:
        sig = score_pair(left, right)
        confidence = compute_confidence(sig)
        status = determine_status(confidence)
        explanation = _build_explanation(sig, confidence, status)
        left_id = str(left["normalized_record_id"])
        right_id = str(right["normalized_record_id"])
        if right_id < left_id:
            left, right = right, left
            left_id, right_id = right_id, left_id
        row = {
            "processing_run_id": processing_run_id,
            "left_normalized_record_id": left_id,
            "right_normalized_record_id": right_id,
            "block_type": "PAN"
            if sig.pan_match
            else "GSTIN"
            if sig.gstin_match
            else "PIN"
            if sig.pin_match
            else "NAME_BUCKET",
            "match_tier": "EXACT"
            if sig.pan_match or sig.gstin_match
            else "STRONG"
            if confidence > 80
            else "WEAK",
            "score": confidence,
            "confidence": confidence,
            "auto_action": "AUTO_MERGE" if status == "AUTO_MERGED" else "REVIEW" if status == "IN_REVIEW" else "IGNORE",
            "decision_state": "PENDING" if status == "IN_REVIEW" else status,
            "reason_codes": {
                "pan_match": sig.pan_match,
                "gstin_match": sig.gstin_match,
                "same_pin": sig.pin_match,
            },
            "signal_weights": {
                "name_phonetic": sig.name_phonetic_score,
                "name_fuzzy": sig.name_fuzzy_score,
                "embedding": sig.embedding_score,
                "address": sig.address_score,
            },
            "explanation": explanation,
            "left_record_snapshot": left,
            "right_record_snapshot": right,
        }
        saved = queries.insert_match_edge(row)
        row["match_edge_id"] = saved.get("match_edge_id") if saved else None
        row["decision_state"] = saved.get("decision_state") if saved else row["decision_state"]
        scored.append(row)
        if status == "IN_REVIEW":
            queries.enqueue_review(saved["match_edge_id"])
    auto_pairs = [(r["left_normalized_record_id"], r["right_normalized_record_id"]) for r in scored if r["decision_state"] == "AUTO_MERGED"]
    auto_ids = [rid for pair in auto_pairs for rid in pair]
    if auto_ids:
        roots = _union_find(auto_ids, auto_pairs)
        clusters: dict[str, list[dict]] = {}
        by_id = {str(r["normalized_record_id"]): r for r in records}
        for rid, root in roots.items():
            clusters.setdefault(root, []).append(by_id[rid])
        for members in clusters.values():
            _create_cluster_and_ubid(members, processing_run_id)
    auto_linked = sum(1 for row in scored if row["decision_state"] == "AUTO_MERGED")
    review = sum(1 for row in scored if row["decision_state"] == "PENDING")
    rejected = sum(1 for row in scored if row["decision_state"] == "REJECTED")
    queries.log_audit(
        "RESOLUTION_RUN",
        f"Processed {len(records)} records -> {len(scored)} candidate pairs",
        confidence=auto_linked / max(len(scored), 1),
        justification=f"auto={auto_linked}, review={review}, rejected={rejected}",
        entity_type="SYSTEM",
    )
    return {
        "total_records": len(records),
        "total_pairs": len(scored),
        "auto_linked": auto_linked,
        "review": review,
        "rejected": rejected,
    }
