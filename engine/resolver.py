"""
ApexForge AI — Entity Resolution Engine
3-stage hybrid pipeline:
  Stage 1 → Deterministic blocking (PAN/GSTIN + phonetic + PIN)
  Stage 2 → Embedding similarity (sentence-transformers, local)
  Stage 3 → Composite confidence scoring + graph-boost propagation

Design principles:
- Conservative defaults: uncertain pairs → human review queue
- Every score is auditable: all signals stored per-pair
- Active-learning ready: reviewer labels feed back into threshold adaptation
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
from dataclasses import dataclass, field
from typing import Any

import jellyfish
from loguru import logger
from rapidfuzz import fuzz
from unidecode import unidecode

from db import queries
from models.embedding_model import get_model

# ─── Thresholds (read from DB via active-learning; these are startup defaults) ─
THRESHOLD_AUTO   = float(__import__("os").getenv("THRESHOLD_AUTO_LINK", 0.92))
THRESHOLD_REVIEW = float(__import__("os").getenv("THRESHOLD_REVIEW",   0.65))

# ─── Signal weights (Bayesian ensemble) ─────────────────────────────────────
WEIGHTS = {
    "pan_match":           0.35,
    "gstin_match":         0.30,
    "name_phonetic_score": 0.10,
    "name_fuzzy_score":    0.10,
    "embedding_score":     0.20,
    "pin_match":           0.05,
    "address_score":       0.05,
    "graph_boost":         0.10,
}
# Note: weights are normalised internally so sum > 1 is fine (bonus signals).


# ═══════════════════════════════════════════════════════════════════════════
# TEXT NORMALISATION
# ═══════════════════════════════════════════════════════════════════════════

_NOISE = re.compile(r"\b(pvt|ltd|private|limited|llp|company|co|corp|industries|"
                    r"enterprises|exports|imports|works|and|&|the|a|an|of)\b", re.I)
_PUNCT = re.compile(r"[^a-z0-9\s]")


def normalize_name(name: str) -> str:
    """
    Normalise a business name for fuzzy comparison.
    Transliterates Indic → ASCII, removes noise words, collapses whitespace.
    """
    n = unidecode(name).lower()
    n = _NOISE.sub(" ", n)
    n = _PUNCT.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip()


def metaphone_key(name: str) -> str:
    """Double Metaphone key for phonetic blocking."""
    return jellyfish.metaphone(normalize_name(name))


def fuzzy_ratio(a: str, b: str) -> float:
    """Token-sort fuzzy ratio normalised to 0-1."""
    return fuzz.token_sort_ratio(a, b) / 100.0


def address_similarity(a: str, b: str) -> float:
    """Partial address match — tolerant of abbreviations."""
    if not a or not b:
        return 0.0
    a_n = normalize_name(a)
    b_n = normalize_name(b)
    return fuzz.partial_ratio(a_n, b_n) / 100.0


# ═══════════════════════════════════════════════════════════════════════════
# STAGE 1 — BLOCKING
# Reduce the O(n²) comparison space by grouping records into blocks.
# ═══════════════════════════════════════════════════════════════════════════

def build_blocks(records: list[dict]) -> dict[str, list[dict]]:
    """
    Returns a dict of block_key → [records] where every record in a block
    is a candidate match with every other.

    Blocking strategy (in priority order):
      B1: Exact PAN  → instant deterministic block
      B2: Exact GSTIN
      B3: PIN code + first Metaphone token of name
      B4: PIN code + first 3 chars of normalised name
    """
    blocks: dict[str, list[dict]] = {}

    for rec in records:
        keys: set[str] = set()

        pan   = (rec.get("pan")   or "").strip().upper()
        gstin = (rec.get("gstin") or "").strip().upper()
        pin   = (rec.get("pin_code") or "").strip()
        name  = normalize_name(rec.get("business_name") or "")
        meta  = metaphone_key(name)

        if pan   and len(pan)   == 10:  keys.add(f"PAN:{pan}")
        if gstin and len(gstin) == 15:  keys.add(f"GSTIN:{gstin}")
        if pin and meta:                 keys.add(f"PIN_META:{pin}:{meta}")
        if pin and len(name) >= 3:      keys.add(f"PIN_NAME:{pin}:{name[:3]}")

        for k in keys:
            blocks.setdefault(k, []).append(rec)

    # Discard trivial blocks (size 1 — no pairs)
    return {k: v for k, v in blocks.items() if len(v) > 1}


def get_candidate_pairs(records: list[dict]) -> list[tuple[dict, dict]]:
    """
    Generate unique candidate pairs from blocks.
    Deduplicates across overlapping blocks using a seen-set.
    """
    blocks = build_blocks(records)
    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[dict, dict]] = []

    for block_records in blocks.values():
        for a, b in itertools.combinations(block_records, 2):
            # Canonical ordering: smaller UUID first
            key = (min(str(a["id"]), str(b["id"])), max(str(a["id"]), str(b["id"])))
            if key not in seen:
                seen.add(key)
                pairs.append((a, b))

    logger.info(f"Blocking: {len(records)} records → {len(pairs)} candidate pairs")
    return pairs


# ═══════════════════════════════════════════════════════════════════════════
# STAGE 2 — SIGNAL SCORING
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class MatchSignals:
    """All individual signals for a pair of records."""
    pan_match:            bool  = False
    gstin_match:          bool  = False
    name_phonetic_score:  float = 0.0
    name_fuzzy_score:     float = 0.0
    embedding_score:      float = 0.0
    pin_match:            bool  = False
    address_score:        float = 0.0
    graph_boost:          float = 0.0   # filled in Stage 3


def score_pair(a: dict, b: dict) -> MatchSignals:
    """Compute all signals between two records."""
    sig = MatchSignals()

    pan_a = (a.get("pan") or "").strip().upper()
    pan_b = (b.get("pan") or "").strip().upper()
    if pan_a and pan_b and len(pan_a) == 10:
        sig.pan_match = (pan_a == pan_b)

    gst_a = (a.get("gstin") or "").strip().upper()
    gst_b = (b.get("gstin") or "").strip().upper()
    if gst_a and gst_b and len(gst_a) == 15:
        sig.gstin_match = (gst_a == gst_b)

    name_a = normalize_name(a.get("business_name") or "")
    name_b = normalize_name(b.get("business_name") or "")
    sig.name_phonetic_score = 1.0 if (name_a and name_b and
                                       metaphone_key(name_a) == metaphone_key(name_b)) else 0.0
    sig.name_fuzzy_score    = fuzzy_ratio(name_a, name_b)

    # Embedding similarity (cosine — vectors already normalised)
    emb_a = a.get("embedding")
    emb_b = b.get("embedding")
    if emb_a and emb_b:
        model = get_model()
        sig.embedding_score = model.cosine_similarity(emb_a, emb_b)

    pin_a = (a.get("pin_code") or "").strip()
    pin_b = (b.get("pin_code") or "").strip()
    sig.pin_match = bool(pin_a and pin_b and pin_a == pin_b)

    sig.address_score = address_similarity(
        a.get("address") or "", b.get("address") or ""
    )

    return sig


# ═══════════════════════════════════════════════════════════════════════════
# STAGE 3 — CONFIDENCE SCORING + GRAPH BOOST
# ═══════════════════════════════════════════════════════════════════════════

def compute_confidence(sig: MatchSignals) -> float:
    """
    Bayesian ensemble score.
    Deterministic anchors (PAN/GSTIN exact match) override everything.
    """
    # Hard anchor: exact PAN or GSTIN → maximal confidence
    if sig.pan_match or sig.gstin_match:
        return min(1.0, 0.92 + 0.04 * sig.pin_match + 0.04 * sig.name_fuzzy_score)

    # Weighted sum of soft signals
    score = (
        sig.name_phonetic_score * WEIGHTS["name_phonetic_score"] +
        sig.name_fuzzy_score    * WEIGHTS["name_fuzzy_score"]    +
        sig.embedding_score     * WEIGHTS["embedding_score"]     +
        sig.pin_match           * WEIGHTS["pin_match"]           +
        sig.address_score       * WEIGHTS["address_score"]       +
        sig.graph_boost         * WEIGHTS["graph_boost"]
    )
    return round(min(score, 0.91), 4)   # cap below auto-link (reserved for deterministic)


def apply_graph_boost(pairs: list[dict]) -> list[dict]:
    """
    Transitive confidence propagation: if A↔B and B↔C are high-confidence,
    boost A↔C slightly (with decay factor 0.5).
    This simulates Label Propagation without a GNN.
    """
    DECAY = 0.5
    # Build adjacency: record_id → list of (partner_id, confidence)
    adj: dict[str, list[tuple[str, float]]] = {}
    for p in pairs:
        a, b, c = p["record_a_id"], p["record_b_id"], p["confidence"]
        adj.setdefault(a, []).append((b, c))
        adj.setdefault(b, []).append((a, c))

    for p in pairs:
        a_id, b_id = p["record_a_id"], p["record_b_id"]
        max_indirect = 0.0
        # 1-hop transitive paths through common neighbours
        a_neighbours = {n: c for n, c in adj.get(a_id, [])}
        b_neighbours = {n: c for n, c in adj.get(b_id, [])}
        common = set(a_neighbours.keys()) & set(b_neighbours.keys())
        for mid in common:
            indirect = a_neighbours[mid] * b_neighbours[mid] * DECAY
            max_indirect = max(max_indirect, indirect)
        p["graph_boost"] = round(max_indirect, 4)
        # Recompute confidence with boost
        sig = MatchSignals(
            pan_match            = p.get("pan_match", False),
            gstin_match          = p.get("gstin_match", False),
            name_phonetic_score  = p.get("name_phonetic_score", 0.0),
            name_fuzzy_score     = p.get("name_fuzzy_score", 0.0),
            embedding_score      = p.get("embedding_score", 0.0),
            pin_match            = p.get("pin_match", False),
            address_score        = p.get("address_score", 0.0),
            graph_boost          = max_indirect,
        )
        p["confidence"] = compute_confidence(sig)

    return pairs


def determine_status(confidence: float) -> str:
    if confidence >= THRESHOLD_AUTO:
        return "AUTO_LINKED"
    if confidence >= THRESHOLD_REVIEW:
        return "REVIEW"
    return "REJECTED"


# ═══════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════

def run_resolution(records: list[dict] | None = None,
                   pin_code: str | None = None) -> dict[str, Any]:
    """
    Full entity-resolution pipeline.
    Returns stats dict: {total_pairs, auto_linked, review, rejected}
    """
    if records is None:
        records = queries.get_records_for_blocking(pin_code)

    if len(records) < 2:
        logger.info("Not enough records to resolve.")
        return {"total_pairs": 0, "auto_linked": 0, "review": 0, "rejected": 0}

    logger.info(f"Starting resolution on {len(records)} records…")

    # Stage 1: Blocking
    pairs_raw = get_candidate_pairs(records)

    # Stage 2: Score all pairs
    scored: list[dict] = []
    for a, b in pairs_raw:
        sig = score_pair(a, b)
        status = determine_status(compute_confidence(sig))
        scored.append({
            "record_a_id":          str(a["id"]),
            "record_b_id":          str(b["id"]),
            "pan_match":            sig.pan_match,
            "gstin_match":          sig.gstin_match,
            "name_phonetic_score":  sig.name_phonetic_score,
            "name_fuzzy_score":     sig.name_fuzzy_score,
            "embedding_score":      sig.embedding_score,
            "pin_match":            sig.pin_match,
            "address_score":        sig.address_score,
            "graph_boost":          0.0,
            "confidence":           compute_confidence(sig),
            "match_status":         status,
            "explanation":          json.dumps({}),
        })

    # Stage 3: Graph boost
    scored = apply_graph_boost(scored)

    # Re-determine status after boost
    auto_linked = review = rejected = 0
    for p in scored:
        p["match_status"] = determine_status(p["confidence"])
        if p["match_status"] == "AUTO_LINKED": auto_linked += 1
        elif p["match_status"] == "REVIEW":    review += 1
        else:                                   rejected += 1

    # Persist matches
    for p in scored:
        from engine.explainability import generate_explanation
        p["explanation"] = json.dumps(generate_explanation(p))
        queries.insert_match(p)

    # Auto-link high-confidence pairs → create/update UBID entities
    _auto_create_entities([p for p in scored if p["match_status"] == "AUTO_LINKED"], records)

    # Populate review queue
    for p in scored:
        if p["match_status"] == "REVIEW":
            mid = queries.insert_match(p)   # returns existing id or new
            if mid:
                try:
                    queries.enqueue_review(mid)
                except Exception:
                    pass

    stats = {
        "total_records": len(records),
        "total_pairs":   len(scored),
        "auto_linked":   auto_linked,
        "review":        review,
        "rejected":      rejected,
    }
    logger.info(f"Resolution complete: {stats}")
    queries.log_audit(
        "RESOLUTION_RUN", f"Processed {len(records)} records → {len(scored)} pairs",
        confidence=auto_linked / max(len(scored), 1)
    )
    return stats


def _auto_create_entities(auto_pairs: list[dict], all_records: list[dict]) -> None:
    """Union-Find: group auto-linked pairs into UBID clusters and persist."""
    import uuid

    rec_by_id = {str(r["id"]): r for r in all_records}
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent.get(x, x), x)
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        parent[find(x)] = find(y)

    for p in auto_pairs:
        union(p["record_a_id"], p["record_b_id"])

    # Group by cluster root
    clusters: dict[str, list[str]] = {}
    for rid in set([p["record_a_id"] for p in auto_pairs] + [p["record_b_id"] for p in auto_pairs]):
        root = find(rid)
        clusters.setdefault(root, []).append(rid)

    for root, record_ids in clusters.items():
        recs = [rec_by_id[rid] for rid in record_ids if rid in rec_by_id]
        if not recs:
            continue

        # Pick canonical: prefer PAN-holding record
        canonical = sorted(recs, key=lambda r: (not bool(r.get("pan")), r.get("business_name", "")))[0]
        depts = list(set(r.get("department_code", "") for r in recs))
        conf  = sum(p["confidence"] for p in auto_pairs if p["record_a_id"] in record_ids) / max(len(auto_pairs), 1)

        entity = {
            "ubid":            str(uuid.uuid4()),
            "canonical_name":  canonical.get("business_name", ""),
            "pan":             canonical.get("pan"),
            "gstin":           canonical.get("gstin"),
            "pin_code":        canonical.get("pin_code"),
            "address":         canonical.get("address"),
            "sector":          canonical.get("sector"),
            "departments":     depts,
            "record_count":    len(recs),
            "confidence_score": round(min(conf, 1.0), 4),
        }
        ubid = queries.create_entity(entity)
        for rid in record_ids:
            queries.link_record_to_entity(ubid, rid, conf)
        queries.log_audit("ENTITY_CREATED", f"Auto-linked {len(recs)} records",
                          entity_ubid=ubid, confidence=conf)
