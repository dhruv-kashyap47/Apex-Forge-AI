"""In-memory demo datastore used when PostgreSQL is unavailable.

The goal is to keep the Streamlit app fully runnable in a minimal Python
environment while preserving the public query API of the project.
"""

from __future__ import annotations

import hashlib
import json
import random
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher


NOW = datetime.now(timezone.utc)
DEPARTMENTS = ["GST", "LABOUR", "FACTORIES", "KSPCB"]
PIN_CODES = ["560001", "560058"]
SECTORS = [
    "Textiles",
    "Garments",
    "Chemicals",
    "Pharmaceuticals",
    "Electronics",
    "Auto Components",
    "Food Processing",
    "Plastics",
    "Metal Fabrication",
    "IT Services",
    "Printing",
    "Packaging",
    "Steel Works",
    "Electrical Equipment",
]
EVENT_TYPES_BY_DEPT = {
    "GST": ["FILING", "RENEWAL", "INSPECTION"],
    "LABOUR": ["INSPECTION", "RENEWAL", "COMPLAINT"],
    "FACTORIES": ["INSPECTION", "RENEWAL", "UTILITY", "SHUTDOWN"],
    "KSPCB": ["INSPECTION", "RENEWAL", "COMPLAINT", "FILING"],
}
EVENT_WEIGHTS = {
    "RENEWAL": 1.0,
    "INSPECTION": 0.9,
    "FILING": 0.8,
    "UTILITY": 0.7,
    "COMPLAINT": 0.3,
    "SHUTDOWN": -2.0,
}


def _stable_uuid(*parts: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "::".join(parts)))


def _normalize(text: str) -> str:
    return " ".join(
        "".join(ch.lower() if ch.isalnum() else " " for ch in str(text))
        .split()
    )


def _metaphone_like(text: str) -> str:
    cleaned = "".join(ch.lower() for ch in text if ch.isalpha())
    if not cleaned:
        return ""
    mapping = str.maketrans(
        {
            "b": "1",
            "f": "1",
            "p": "1",
            "v": "1",
            "c": "2",
            "g": "2",
            "j": "2",
            "k": "2",
            "q": "2",
            "s": "2",
            "x": "2",
            "z": "2",
            "d": "3",
            "t": "3",
            "l": "4",
            "m": "5",
            "n": "5",
            "r": "6",
        }
    )
    encoded = cleaned[1:].translate(mapping)
    result = []
    prev = None
    for char in encoded:
        if char != prev:
            result.append(char)
        prev = char
    return cleaned[0].upper() + "".join(result)[:6]


def _token_sort_ratio(a: str, b: str) -> float:
    a_s = " ".join(sorted(_normalize(a).split()))
    b_s = " ".join(sorted(_normalize(b).split()))
    return SequenceMatcher(None, a_s, b_s).ratio()


def _partial_ratio(a: str, b: str) -> float:
    a_n = _normalize(a)
    b_n = _normalize(b)
    if not a_n or not b_n:
        return 0.0
    if len(a_n) > len(b_n):
        a_n, b_n = b_n, a_n
    span = len(a_n)
    best = 0.0
    for idx in range(0, max(len(b_n) - span + 1, 1)):
        best = max(best, SequenceMatcher(None, a_n, b_n[idx : idx + span]).ratio())
    return best


def _generate_name(rng: random.Random) -> str:
    prefixes = ["Shri", "Sri", "M/s", "Karnataka", "Mysore", "Bengaluru"]
    surnames = ["Reddy", "Gowda", "Shetty", "Rao", "Patel", "Murthy", "Iyer", "Nair"]
    types = ["Industries", "Enterprises", "Works", "Forge", "Tech", "Services", "Traders"]
    parts = []
    if rng.random() < 0.3:
        parts.append(rng.choice(prefixes))
    parts.extend([rng.choice(surnames), rng.choice(types)])
    return " ".join(parts)


def _noise(text: str, rng: random.Random, level: float = 0.3) -> str:
    if rng.random() > level:
        return text
    transforms = [
        lambda n: n.replace("Industries", "Inds").replace("Enterprises", "Ent"),
        lambda n: n.lower(),
        lambda n: n.upper(),
        lambda n: n.replace(" ", "  "),
        lambda n: n[:3] + "." + n[4:] if len(n) > 5 else n,
        lambda n: n + f" ({rng.choice(['Unit 1', 'Regd', 'Branch'])})",
    ]
    return rng.choice(transforms)(text)


def _time_decay(event_date: datetime | None, half_life_days: int = 180) -> float:
    if not event_date:
        return 0.0
    if event_date.tzinfo is None:
        event_date = event_date.replace(tzinfo=timezone.utc)
    days_ago = max((NOW - event_date).days, 0)
    return 2 ** (-(days_ago / half_life_days))


def _classify_vitality(events: list[dict]) -> tuple[str, float, int]:
    signals = Counter(ev["event_type"] for ev in events)
    total_events = len(events)
    if not events:
        return "UNKNOWN", 0.0, 0
    if signals.get("SHUTDOWN", 0) > 0:
        status = "CLOSED"
    elif sum(1 for ev in events if ev["event_date"] > NOW - timedelta(days=180)) >= 2:
        status = "ACTIVE"
    elif sum(1 for ev in events if ev["event_date"] > NOW - timedelta(days=365)) >= 1:
        status = "ACTIVE"
    else:
        status = "DORMANT"

    weighted_sum = sum(EVENT_WEIGHTS.get(ev["event_type"], 0.5) * _time_decay(ev["event_date"]) for ev in events)
    max_possible = max(total_events * 1.0, 1.0)
    vitality_score = min(max(weighted_sum / max_possible, 0.0), 1.0)
    if status == "CLOSED":
        vitality_score = max(vitality_score * 0.1, 0.02)

    last_event = max(ev["event_date"] for ev in events)
    recency = _time_decay(last_event)
    diversity = min(len(signals) / max(len(EVENT_WEIGHTS), 1), 1.0)
    pulse = max(0, min(100, round(vitality_score * 70 + recency * 20 + diversity * 10)))
    return status, round(vitality_score, 4), pulse


@dataclass
class DemoStore:
    raw_records: dict[str, dict]
    entities: dict[str, dict]
    record_links: dict[str, dict]
    entity_matches: dict[tuple[str, str], dict]
    activity_events: list[dict]
    review_queue: dict[int, dict]
    audit_log: list[dict]
    users: list[dict]
    _id_seq: int
    _match_seq: int
    _audit_seq: int

    def __init__(self) -> None:
        self.raw_records = {}
        self.entities = {}
        self.record_links = {}
        self.entity_matches = {}
        self.activity_events = []
        self.review_queue = {}
        self.audit_log = []
        self.users = [
            {"username": "admin", "full_name": "System Administrator", "role": "admin"},
            {"username": "reviewer1", "full_name": "Priya Sharma", "role": "reviewer"},
            {"username": "reviewer2", "full_name": "Rajan Nair", "role": "reviewer"},
            {"username": "demo", "full_name": "Demo Officer", "role": "reviewer"},
        ]
        self._id_seq = 1
        self._match_seq = 1
        self._audit_seq = 1
        self._seed()

    # ------------------------------------------------------------------
    # Seeding
    # ------------------------------------------------------------------
    def _seed(self) -> None:
        rng = random.Random(42)
        masters = self._generate_master_businesses(rng, 72)
        for master in masters:
            self._seed_master(master, rng)

    def _generate_master_businesses(self, rng: random.Random, n: int) -> list[dict]:
        masters = []
        for idx in range(n):
            name = _generate_name(rng)
            pan = self._rand_pan(rng) if rng.random() < 0.75 else None
            gstin = self._rand_gstin(rng, pan) if pan and rng.random() < 0.8 else None
            pin_code = rng.choice(PIN_CODES)
            sector = rng.choice(SECTORS)
            profile = self._assign_profile(rng)
            masters.append(
                {
                    "master_id": _stable_uuid("master", str(idx), name, pin_code),
                    "canonical_name": name,
                    "pan": pan,
                    "gstin": gstin,
                    "pin_code": pin_code,
                    "address": f"No.{rng.randint(1,999)}, {rng.choice(['MG Road', 'Whitefield Main Road', 'Brigade Road', 'Industrial Area'])}, Bengaluru - {pin_code}",
                    "sector": sector,
                    "registration_date": NOW.date() - timedelta(days=rng.randint(365, 3650)),
                    "vitality_profile": profile,
                }
            )
        return masters

    def _assign_profile(self, rng: random.Random) -> str:
        r = rng.random()
        if r < 0.55:
            return "active"
        if r < 0.75:
            return "dormant"
        if r < 0.88:
            return "recently_active"
        return "closed"

    def _rand_pan(self, rng: random.Random) -> str:
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        digits = "0123456789"
        return rng.choice(letters) * 5 + "".join(rng.choice(digits) for _ in range(4)) + rng.choice(letters)

    def _rand_gstin(self, rng: random.Random, pan: str | None) -> str:
        if not pan:
            pan = self._rand_pan(rng)
        return f"29{pan}{rng.randint(1,9)}Z{rng.choice('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')}"

    def _seed_master(self, master: dict, rng: random.Random) -> None:
        dept_count = rng.randint(1, 4) if rng.random() < 0.35 else 1
        departments = rng.sample(DEPARTMENTS, dept_count)
        entity_ubid = _stable_uuid("entity", master["master_id"])
        entity = {
            "ubid": entity_ubid,
            "canonical_name": master["canonical_name"],
            "pan": master["pan"],
            "gstin": master["gstin"],
            "pin_code": master["pin_code"],
            "address": master["address"],
            "sector": master["sector"],
            "departments": [],
            "record_count": 0,
            "confidence_score": 0.95,
            "vitality_status": "UNKNOWN",
            "vitality_score": 0.0,
            "pulse_score": 0,
            "last_activity_at": None,
            "created_at": NOW,
            "updated_at": NOW,
            "is_active": True,
        }
        self.entities[entity_ubid] = entity

        records = []
        for dept in departments:
            record = self._make_record(master, dept, rng)
            records.append(record)
            self.raw_records[record["id"]] = record
            self.link_record_to_entity(entity_ubid, record["id"], 0.95, "seed")
        entity["departments"] = sorted({rec["department_code"] for rec in records})
        entity["record_count"] = len(records)
        self._seed_events(entity_ubid, records, master["vitality_profile"], rng)
        self._classify_entity(entity_ubid)
        self.log_audit(
            "ENTITY_CREATED",
            f"Seeded entity with {len(records)} records",
            entity_ubid=entity_ubid,
            actor="system",
            confidence=entity["confidence_score"],
        )

        self._seed_matches(entity_ubid, records)

    def _make_record(self, master: dict, dept: str, rng: random.Random) -> dict:
        noisy_name = _noise(master["canonical_name"], rng, 0.35)
        pan = master["pan"] if rng.random() > 0.15 else None
        gstin = master["gstin"] if rng.random() > 0.2 else None
        record_id = _stable_uuid("record", master["master_id"], dept, noisy_name, str(rng.randint(1, 1_000_000)))
        external_id = f"{dept}-{rng.randint(100000, 999999)}"
        record = {
            "id": record_id,
            "department_code": dept,
            "external_id": external_id,
            "business_name": noisy_name,
            "normalized_name": noisy_name.lower().strip(),
            "pan": pan,
            "gstin": gstin,
            "address": _noise(master["address"], rng, 0.2),
            "pin_code": master["pin_code"],
            "sector": master["sector"],
            "phone": f"+91-{rng.randint(600,999)}-{rng.randint(100,999)}-{rng.randint(1000,9999)}",
            "email": None,
            "registration_date": master["registration_date"],
            "status_raw": self._dept_status(dept, master["vitality_profile"]),
            "extra_data": self._dept_extra(dept, rng),
            "record_hash": hashlib.sha256(f"{dept}||{external_id}||{noisy_name}".encode()).hexdigest(),
            "embedding": self._embedding_text(noisy_name, master["sector"], master["pin_code"], dept, master["address"]),
        }
        return record

    def _embedding_text(self, *parts: str) -> list[float]:
        text = " | ".join(part for part in parts if part)
        vec = [0.0] * 384
        if not text:
            return vec
        tokens = [tok for tok in _normalize(text).split() if tok]
        if not tokens:
            tokens = [text.lower()]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for offset in range(0, 32, 4):
                idx = int.from_bytes(digest[offset : offset + 4], "big") % 384
                vec[idx] += 1.0
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def _dept_status(self, dept: str, profile: str) -> str:
        mapping = {
            "active": {"GST": "Active", "LABOUR": "Valid", "FACTORIES": "Operating", "KSPCB": "Consent Valid"},
            "dormant": {"GST": "Inactive", "LABOUR": "Suspended", "FACTORIES": "Idle", "KSPCB": "Consent Expired"},
            "recently_active": {"GST": "Active", "LABOUR": "Valid", "FACTORIES": "Operating", "KSPCB": "Under Renewal"},
            "closed": {"GST": "Cancelled", "LABOUR": "Closed", "FACTORIES": "Surrendered", "KSPCB": "Consent Revoked"},
        }
        return mapping.get(profile, {}).get(dept, "Unknown")

    def _dept_extra(self, dept: str, rng: random.Random) -> dict:
        if dept == "GST":
            return {"gst_category": rng.choice(["Regular", "Composition", "TDS"]), "turnover_band": rng.choice(["<40L", "40L-1.5Cr", ">1.5Cr"])}
        if dept == "LABOUR":
            return {"employees": rng.randint(5, 500), "contract_workers": rng.randint(0, 50)}
        if dept == "FACTORIES":
            return {"power_kw": rng.randint(10, 5000), "category": rng.choice(["Small", "Medium", "Large"])}
        if dept == "KSPCB":
            return {"consent_type": rng.choice(["Orange", "Red", "Green"]), "effluent_volume_kld": rng.randint(0, 200)}
        return {}

    def _seed_events(self, ubid: str, records: list[dict], profile: str, rng: random.Random) -> None:
        schedule = {
            "active": (4, 10, 365),
            "recently_active": (2, 6, 540),
            "dormant": (0, 3, 1095),
            "closed": (0, 2, 1800),
        }.get(profile, (0, 2, 900))
        min_count, max_count, max_days = schedule
        for record in records:
            count = rng.randint(min_count, max_count)
            for _ in range(count):
                etype = rng.choice(EVENT_TYPES_BY_DEPT.get(record["department_code"], ["INSPECTION"]))
                if profile == "closed" and rng.random() < 0.6:
                    etype = "SHUTDOWN"
                event_date = NOW - timedelta(days=rng.randint(0, max_days))
                self.activity_events.append(
                    {
                        "id": len(self.activity_events) + 1,
                        "ubid": ubid,
                        "raw_record_id": record["id"],
                        "department_code": record["department_code"],
                        "event_type": etype,
                        "event_date": event_date,
                        "signal_strength": EVENT_WEIGHTS.get(etype, 0.5),
                        "details": {"source": record["department_code"], "auto_generated": True},
                        "created_at": NOW,
                    }
                )

    def _seed_matches(self, ubid: str, records: list[dict]) -> None:
        for i, left in enumerate(records):
            for right in records[i + 1 :]:
                match = self._build_match(left, right)
                self.insert_match(match)

    def _build_match(self, a: dict, b: dict) -> dict:
        pair_hash = int(hashlib.sha256(f"{a['id']}::{b['id']}".encode()).hexdigest(), 16)
        pan_a = (a.get("pan") or "").strip().upper()
        pan_b = (b.get("pan") or "").strip().upper()
        gst_a = (a.get("gstin") or "").strip().upper()
        gst_b = (b.get("gstin") or "").strip().upper()
        name_a = _normalize(a.get("business_name") or "")
        name_b = _normalize(b.get("business_name") or "")
        phonetic = 1.0 if _metaphone_like(name_a) == _metaphone_like(name_b) and name_a and name_b else 0.0
        fuzzy = _token_sort_ratio(name_a, name_b)
        emb_a = a.get("embedding") or []
        emb_b = b.get("embedding") or []
        embedding = float(sum(x * y for x, y in zip(emb_a, emb_b)))
        pin_match = bool((a.get("pin_code") or "") and a.get("pin_code") == b.get("pin_code"))
        address = _partial_ratio(a.get("address") or "", b.get("address") or "")
        if pan_a and pan_b and len(pan_a) == 10:
            confidence = min(1.0, 0.92 + 0.04 * float(pin_match) + 0.04 * fuzzy)
            status = "AUTO_LINKED"
            pan_match = pan_a == pan_b
            gstin_match = gst_a == gst_b and len(gst_a) == 15
        elif gst_a and gst_b and len(gst_a) == 15:
            confidence = min(1.0, 0.92 + 0.04 * float(pin_match) + 0.04 * fuzzy)
            status = "AUTO_LINKED"
            pan_match = False
            gstin_match = gst_a == gst_b
        else:
            score = (
                phonetic * 0.10
                + fuzzy * 0.10
                + embedding * 0.20
                + float(pin_match) * 0.05
                + address * 0.05
            )
            confidence = round(min(score, 0.91), 4)
            if confidence >= 0.65:
                status = "REVIEW"
            elif pair_hash % 7 == 0:
                confidence = round(max(confidence, 0.68 + (pair_hash % 11) * 0.01), 4)
                status = "REVIEW"
            else:
                status = "REJECTED"
            pan_match = False
            gstin_match = False
        return {
            "record_a_id": str(a["id"]),
            "record_b_id": str(b["id"]),
            "pan_match": pan_match,
            "gstin_match": gstin_match,
            "name_phonetic_score": round(phonetic, 4),
            "name_fuzzy_score": round(fuzzy, 4),
            "embedding_score": round(embedding, 4),
            "pin_match": pin_match,
            "address_score": round(address, 4),
            "graph_boost": 0.0,
            "confidence": round(confidence, 4),
            "match_status": status,
            "explanation": {},
            "created_at": NOW,
            "reviewed_at": NOW if status in {"MERGED", "SPLIT", "REJECTED"} else None,
            "reviewed_by": "seed" if status in {"MERGED", "SPLIT", "REJECTED"} else None,
        }

    def _classify_entity(self, ubid: str) -> None:
        entity = self.entities[ubid]
        events = self.get_entity_events(ubid)
        if not events:
            entity.update({"vitality_status": "UNKNOWN", "vitality_score": 0.0, "pulse_score": 0, "last_activity_at": None})
            return
        status, score, pulse = _classify_vitality(events)
        entity.update(
            {
                "vitality_status": status,
                "vitality_score": score,
                "pulse_score": pulse,
                "last_activity_at": max(ev["event_date"] for ev in events),
                "updated_at": NOW,
            }
        )

    # ------------------------------------------------------------------
    # Direct data operations used by db.queries
    # ------------------------------------------------------------------
    @property
    def is_demo_mode(self) -> bool:
        return True

    def upsert_raw_record(self, record: dict) -> str:
        record = dict(record)
        rid = str(record.get("id") or _stable_uuid("raw", record.get("record_hash", json.dumps(record, sort_keys=True))))
        record["id"] = rid
        self.raw_records[rid] = record
        return rid

    def update_record_embedding(self, record_id: str, embedding: list[float]) -> None:
        if record_id in self.raw_records:
            self.raw_records[record_id]["embedding"] = embedding

    def get_records_by_department(self, dept_code: str, limit: int = 1000) -> list[dict]:
        rows = [r for r in self.raw_records.values() if r.get("department_code") == dept_code]
        return sorted(rows, key=lambda r: r.get("ingested_at", NOW), reverse=True)[:limit]

    def get_records_for_blocking(self, pin_code: str | None = None) -> list[dict]:
        rows = list(self.raw_records.values())
        if pin_code:
            rows = [r for r in rows if str(r.get("pin_code") or "") == str(pin_code)]
        return sorted(rows, key=lambda r: (r.get("department_code", ""), r.get("business_name", "")))

    def get_unlinked_records(self) -> list[dict]:
        return [r for r in self.raw_records.values() if r["id"] not in self.record_links]

    def get_similar_records_by_embedding(self, embedding: list[float], top_k: int = 10, exclude_id: str | None = None) -> list[dict]:
        rows = []
        for record in self.raw_records.values():
            if exclude_id and record["id"] == exclude_id:
                continue
            other = record.get("embedding")
            if not other:
                continue
            similarity = float(sum(x * y for x, y in zip(embedding, other)))
            rows.append(
                {
                    "id": record["id"],
                    "business_name": record.get("business_name"),
                    "department_code": record.get("department_code"),
                    "pan": record.get("pan"),
                    "gstin": record.get("gstin"),
                    "pin_code": record.get("pin_code"),
                    "similarity_score": round(similarity, 4),
                }
            )
        return sorted(rows, key=lambda r: r["similarity_score"], reverse=True)[:top_k]

    def insert_match(self, match: dict) -> int | None:
        key = tuple(sorted((str(match["record_a_id"]), str(match["record_b_id"]))))
        existing = self.entity_matches.get(key)
        if existing:
            existing.update(match)
            return existing["id"]
        row = dict(match)
        row["id"] = self._match_seq
        self._match_seq += 1
        self.entity_matches[key] = row
        if row["match_status"] == "REVIEW":
            self.enqueue_review(row["id"])
        return row["id"]

    def enqueue_review(self, match_id: int) -> None:
        self.review_queue[match_id] = {
            "id": len(self.review_queue) + 1,
            "match_id": match_id,
            "priority": 5,
            "assigned_to": None,
            "status": "PENDING",
            "created_at": NOW,
            "completed_at": None,
        }

    def get_pending_matches(self, threshold: float = 0.65, limit: int = 50) -> list[dict]:
        rows = [
            match
            for match in self.entity_matches.values()
            if match.get("match_status") == "REVIEW" and threshold <= float(match.get("confidence", 0.0)) <= 0.92
        ]
        return sorted(rows, key=lambda m: float(m.get("confidence", 0.0)), reverse=True)[:limit]

    def update_match_decision(self, match_id: int, decision: str, reviewer: str, justification: str) -> None:
        for match in self.entity_matches.values():
            if match.get("id") == match_id:
                match["match_status"] = decision
                match["reviewed_by"] = reviewer
                match["reviewed_at"] = NOW
                explanation = match.get("explanation") or {}
                explanation["reviewer_note"] = justification
                explanation["final_decision"] = decision
                match["explanation"] = explanation
                break
        if match_id in self.review_queue:
            self.review_queue[match_id]["status"] = "DONE"
            self.review_queue[match_id]["completed_at"] = NOW

    def get_graph_clusters_cte(self, seed_record_id: str) -> list[dict]:
        entity = self._entity_for_record(seed_record_id)
        if not entity:
            return []
        rows = []
        for link in self.record_links.values():
            if link["ubid"] != entity["ubid"]:
                continue
            record = self.raw_records.get(link["raw_record_id"])
            if not record:
                continue
            confidence = 1.0
            rows.append(
                {
                    "id": record["id"],
                    "business_name": record.get("business_name"),
                    "department_code": record.get("department_code"),
                    "pan": record.get("pan"),
                    "gstin": record.get("gstin"),
                    "pin_code": record.get("pin_code"),
                    "sector": record.get("sector"),
                    "edge_confidence": confidence,
                    "depth": 0,
                }
            )
        return rows

    def get_all_match_edges(self, status_filter: list[str] | None = None) -> list[dict]:
        statuses = set(status_filter or ["AUTO_LINKED", "MERGED", "REVIEW"])
        rows = []
        for match in self.entity_matches.values():
            if match.get("match_status") not in statuses:
                continue
            a = self.raw_records.get(match["record_a_id"], {})
            b = self.raw_records.get(match["record_b_id"], {})
            rows.append(
                {
                    "id": match["id"],
                    "record_a_id": match["record_a_id"],
                    "record_b_id": match["record_b_id"],
                    "confidence": match.get("confidence", 0.0),
                    "match_status": match.get("match_status"),
                    "name_a": a.get("business_name"),
                    "dept_a": a.get("department_code"),
                    "name_b": b.get("business_name"),
                    "dept_b": b.get("department_code"),
                }
            )
        return sorted(rows, key=lambda r: float(r.get("confidence", 0.0)), reverse=True)[:500]

    def create_entity(self, entity: dict) -> str:
        signature = (
            entity.get("canonical_name", "").strip().lower(),
            entity.get("pan") or "",
            entity.get("gstin") or "",
            entity.get("pin_code") or "",
            entity.get("sector") or "",
        )
        for current in self.entities.values():
            current_signature = (
                current.get("canonical_name", "").strip().lower(),
                current.get("pan") or "",
                current.get("gstin") or "",
                current.get("pin_code") or "",
                current.get("sector") or "",
            )
            if current_signature == signature:
                current_departments = set(current.get("departments") or [])
                current_departments.update(entity.get("departments") or [])
                current.update({k: v for k, v in entity.items() if k != "ubid"})
                current["departments"] = sorted(current_departments)
                current["record_count"] = max(int(current.get("record_count", 0)), int(entity.get("record_count", 0)))
                current["confidence_score"] = max(float(current.get("confidence_score", 0.0)), float(entity.get("confidence_score", 0.0)))
                current["updated_at"] = NOW
                return current["ubid"]
        ubid = str(entity.get("ubid") or _stable_uuid("entity", str(self._id_seq), json.dumps(entity, sort_keys=True)))
        self._id_seq += 1
        row = {
            "ubid": ubid,
            "canonical_name": entity.get("canonical_name", ""),
            "pan": entity.get("pan"),
            "gstin": entity.get("gstin"),
            "pin_code": entity.get("pin_code"),
            "address": entity.get("address"),
            "sector": entity.get("sector"),
            "departments": list(entity.get("departments") or []),
            "record_count": int(entity.get("record_count", 1)),
            "confidence_score": float(entity.get("confidence_score", 1.0)),
            "vitality_status": entity.get("vitality_status", "UNKNOWN"),
            "vitality_score": float(entity.get("vitality_score", 0.0)),
            "pulse_score": int(entity.get("pulse_score", 0)),
            "last_activity_at": entity.get("last_activity_at"),
            "created_at": entity.get("created_at", NOW),
            "updated_at": entity.get("updated_at", NOW),
            "is_active": True,
        }
        self.entities[ubid] = row
        return ubid

    def get_entity(self, ubid: str) -> dict | None:
        entity = self.entities.get(ubid)
        if not entity:
            return None
        return self._entity_summary(entity)

    def search_entities(self, query: str, pin_code: str | None = None, vitality: str | None = None, limit: int = 50) -> list[dict]:
        query_l = (query or "").strip().lower()
        rows = []
        for entity in self.entities.values():
            if not entity.get("is_active", True):
                continue
            if query_l:
                if query_l not in str(entity.get("canonical_name", "")).lower() and query_l not in str(entity.get("pan", "")).lower() and query_l not in str(entity.get("gstin", "")).lower() and query_l not in str(entity.get("ubid", "")).lower():
                    continue
            if pin_code and str(entity.get("pin_code") or "") != str(pin_code):
                continue
            if vitality and vitality != "ALL" and entity.get("vitality_status") != vitality:
                continue
            rows.append(self._entity_summary(entity))
        return sorted(rows, key=lambda r: (-float(r.get("confidence_score", 0.0)), str(r.get("canonical_name", ""))))[:limit]

    def _entity_summary(self, entity: dict) -> dict:
        summary = dict(entity)
        summary["linked_records"] = len([1 for link in self.record_links.values() if link["ubid"] == entity["ubid"]])
        summary["total_events"] = len([ev for ev in self.activity_events if ev.get("ubid") == entity["ubid"]])
        summary["latest_event_date"] = max((ev["event_date"] for ev in self.activity_events if ev.get("ubid") == entity["ubid"]), default=None)
        return summary

    def update_entity_vitality(self, ubid: str, status: str, score: float, pulse: int) -> None:
        if ubid in self.entities:
            self.entities[ubid].update(
                {
                    "vitality_status": status,
                    "vitality_score": float(score),
                    "pulse_score": int(pulse),
                    "last_activity_at": self.entities[ubid].get("last_activity_at") or NOW,
                    "updated_at": NOW,
                }
            )

    def link_record_to_entity(self, ubid: str, record_id: str, confidence: float, linked_by: str = "system") -> None:
        self.record_links[str(record_id)] = {
            "ubid": str(ubid),
            "raw_record_id": str(record_id),
            "link_confidence": float(confidence),
            "linked_by": linked_by,
            "linked_at": NOW,
        }

    def get_entity_records(self, ubid: str) -> list[dict]:
        rows = []
        for record_id, link in self.record_links.items():
            if link["ubid"] != ubid:
                continue
            record = self.raw_records.get(record_id)
            if not record:
                continue
            row = dict(record)
            row.update(link)
            rows.append(row)
        return sorted(rows, key=lambda r: str(r.get("department_code", "")))

    def insert_event(self, event: dict) -> None:
        self.activity_events.append(
            {
                "id": len(self.activity_events) + 1,
                "ubid": event.get("ubid"),
                "raw_record_id": event.get("raw_record_id"),
                "department_code": event.get("department_code"),
                "event_type": event.get("event_type"),
                "event_date": event.get("event_date") or NOW,
                "signal_strength": event.get("signal_strength", 1.0),
                "details": event.get("details", {}),
                "created_at": NOW,
            }
        )
        ubid = event.get("ubid")
        if ubid and ubid in self.entities:
            self._classify_entity(ubid)

    def get_entity_events(self, ubid: str) -> list[dict]:
        return sorted([ev for ev in self.activity_events if ev.get("ubid") == ubid], key=lambda ev: ev["event_date"], reverse=True)

    def get_vitality_signals(self, ubid: str) -> dict:
        events = self.get_entity_events(ubid)
        counts = Counter(ev["event_type"] for ev in events)
        last_event = max((ev["event_date"] for ev in events), default=None)
        first_event = min((ev["event_date"] for ev in events), default=None)
        return {
            "total_events": len(events),
            "events_6m": sum(1 for ev in events if ev["event_date"] > NOW - timedelta(days=180)),
            "events_12m": sum(1 for ev in events if ev["event_date"] > NOW - timedelta(days=365)),
            "events_18m": sum(1 for ev in events if ev["event_date"] > NOW - timedelta(days=540)),
            "renewals": counts.get("RENEWAL", 0),
            "inspections": counts.get("INSPECTION", 0),
            "filings": counts.get("FILING", 0),
            "utility_events": counts.get("UTILITY", 0),
            "shutdowns": counts.get("SHUTDOWN", 0),
            "last_event": last_event,
            "first_event": first_event,
            "avg_signal": round(sum(ev.get("signal_strength", 0.0) for ev in events) / max(len(events), 1), 3) if events else 0.0,
        }

    def get_dashboard_stats(self) -> dict:
        summary_rows = list(self.entities.values())
        return {
            "total_entities": len(summary_rows),
            "active_count": sum(1 for e in summary_rows if e.get("vitality_status") == "ACTIVE"),
            "dormant_count": sum(1 for e in summary_rows if e.get("vitality_status") == "DORMANT"),
            "closed_count": sum(1 for e in summary_rows if e.get("vitality_status") == "CLOSED"),
            "unknown_count": sum(1 for e in summary_rows if e.get("vitality_status") == "UNKNOWN"),
            "avg_confidence": round(sum(float(e.get("confidence_score", 0)) for e in summary_rows) / max(len(summary_rows), 1), 3),
            "avg_pulse_score": round(sum(float(e.get("pulse_score", 0)) for e in summary_rows) / max(len(summary_rows), 1), 1),
            "multi_dept_entities": sum(1 for e in summary_rows if len(e.get("departments") or []) > 1),
            "pending_reviews": len([m for m in self.entity_matches.values() if m.get("match_status") == "REVIEW"]),
            "total_raw_records": len(self.raw_records),
            "total_audit_events": len(self.audit_log),
        }

    def get_entities_by_sector(self, limit: int = 20) -> list[dict]:
        sectors: defaultdict[str, dict] = defaultdict(lambda: {"sector": "", "total": 0, "active": 0, "dormant": 0, "closed": 0})
        for entity in self.entities.values():
            sector = entity.get("sector") or "Unknown"
            bucket = sectors[sector]
            bucket["sector"] = sector
            bucket["total"] += 1
            status = entity.get("vitality_status")
            if status in {"ACTIVE", "DORMANT", "CLOSED"}:
                bucket[status.lower()] += 1
        rows = sorted(sectors.values(), key=lambda row: row["total"], reverse=True)
        return rows[:limit]

    def get_vitality_by_pin(self) -> list[dict]:
        buckets: defaultdict[str, dict] = defaultdict(lambda: {"pin_code": "", "total": 0, "active": 0, "dormant": 0, "avg_pulse": 0.0})
        for entity in self.entities.values():
            pin = entity.get("pin_code") or "Unknown"
            bucket = buckets[pin]
            bucket["pin_code"] = pin
            bucket["total"] += 1
            status = entity.get("vitality_status")
            if status == "ACTIVE":
                bucket["active"] += 1
            elif status == "DORMANT":
                bucket["dormant"] += 1
        for bucket in buckets.values():
            bucket["avg_pulse"] = round(sum(float(e.get("pulse_score", 0)) for e in self.entities.values() if (e.get("pin_code") or "Unknown") == bucket["pin_code"]) / max(bucket["total"], 1), 1)
        return sorted(buckets.values(), key=lambda row: row["total"], reverse=True)

    def get_audit_trail(self, entity_ubid: str | None = None, limit: int = 100) -> list[dict]:
        rows = self.audit_log
        if entity_ubid:
            rows = [row for row in rows if row.get("entity_ubid") == entity_ubid]
        return sorted(rows, key=lambda row: row.get("created_at") or NOW, reverse=True)[:limit]

    def log_audit(
        self,
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
        self.audit_log.append(
            {
                "id": self._audit_seq,
                "event_type": event_type,
                "entity_ubid": entity_ubid,
                "match_id": match_id,
                "actor": actor,
                "action": action,
                "before_state": before,
                "after_state": after,
                "confidence": confidence,
                "justification": justification,
                "created_at": NOW,
            }
        )
        self._audit_seq += 1

    def get_threshold_stats(self) -> dict:
        reviewed = [match for match in self.entity_matches.values() if match.get("reviewed_at")]
        merges = [match for match in reviewed if match.get("match_status") == "MERGED"]
        rejects = [match for match in reviewed if match.get("match_status") in {"SPLIT", "REJECTED"}]
        return {
            "avg_merge_confidence": round(sum(float(m.get("confidence", 0)) for m in merges) / max(len(merges), 1), 3) if merges else 0.0,
            "avg_reject_confidence": round(sum(float(m.get("confidence", 0)) for m in rejects) / max(len(rejects), 1), 3) if rejects else 0.0,
            "total_merges": len(merges),
            "total_rejects": len(rejects),
            "min_merge_confidence": min((float(m.get("confidence", 0)) for m in merges), default=0.0),
            "max_reject_confidence": max((float(m.get("confidence", 0)) for m in rejects), default=0.0),
        }

    def get_learning_labels(self) -> list[dict]:
        rows = []
        for match in self.entity_matches.values():
            if match.get("match_status") in {"MERGED", "SPLIT", "REJECTED"} and match.get("reviewed_at"):
                rows.append(
                    {
                        "id": match["id"],
                        "confidence": match.get("confidence", 0.0),
                        "match_status": match.get("match_status"),
                        "pan_match": match.get("pan_match", False),
                        "gstin_match": match.get("gstin_match", False),
                        "name_phonetic_score": match.get("name_phonetic_score", 0.0),
                        "name_fuzzy_score": match.get("name_fuzzy_score", 0.0),
                        "embedding_score": match.get("embedding_score", 0.0),
                        "pin_match": match.get("pin_match", False),
                        "address_score": match.get("address_score", 0.0),
                        "reviewer_label": 1 if match.get("match_status") == "MERGED" else 0,
                        "reviewed_by": match.get("reviewed_by"),
                        "reviewed_at": match.get("reviewed_at"),
                    }
                )
        return sorted(rows, key=lambda row: row.get("reviewed_at") or NOW, reverse=True)

    def run_structured_query(self, params: dict) -> list[dict]:
        rows = self.search_entities("", pin_code=params.get("pin_code"), vitality=params.get("vitality"), limit=10_000)
        if params.get("sector"):
            needle = str(params["sector"]).lower()
            rows = [row for row in rows if needle in str(row.get("sector", "")).lower()]
        if params.get("dept"):
            rows = [row for row in rows if params["dept"] in (row.get("departments") or [])]
        if params.get("no_inspection_months"):
            months = int(params["no_inspection_months"])
            cutoff = NOW - timedelta(days=30 * months)
            filtered = []
            for row in rows:
                latest_inspection = max(
                    (ev["event_date"] for ev in self.activity_events if ev.get("ubid") == row["ubid"] and ev.get("event_type") == "INSPECTION"),
                    default=None,
                )
                if not latest_inspection or latest_inspection <= cutoff:
                    filtered.append(row)
            rows = filtered
        limit = min(int(params.get("limit", 50)), 500)
        return rows[:limit]

    def count_raw_records(self) -> int:
        return len(self.raw_records)

    def count_entities(self) -> int:
        return len(self.entities)

    def count_activity_events(self) -> int:
        return len(self.activity_events)

    def count_audit_log(self) -> int:
        return len(self.audit_log)

    def count_pending_reviews(self) -> int:
        return len([row for row in self.review_queue.values() if row.get("status") == "PENDING"])

    def get_active_entity_ids(self, limit: int = 5000) -> list[dict]:
        rows = [entity for entity in self.entities.values() if entity.get("is_active", True)]
        return [{"ubid": row["ubid"]} for row in rows[:limit]]

    def health_check(self) -> bool:
        return True

    def execute_sql(self, sql: str, params: tuple | dict | None = None) -> list[dict]:
        normalized = " ".join(str(sql).strip().lower().split())
        params = params or ()
        if normalized == "select 1 as ok":
            return [{"ok": 1}]
        if normalized == "select count(*) as n from raw_records":
            return [{"n": self.count_raw_records()}]
        if normalized == "select count(*) as n from entities":
            return [{"n": self.count_entities()}]
        if normalized == "select count(*) as n from activity_events":
            return [{"n": self.count_activity_events()}]
        if normalized == "select count(*) as n from audit_log":
            return [{"n": self.count_audit_log()}]
        if normalized == "select count(*) as n from review_queue where status='pending'":
            return [{"n": self.count_pending_reviews()}]
        if normalized.startswith("select ubid from entities where is_active = true limit"):
            limit = int(params[0] if isinstance(params, tuple) and params else 5000)
            return self.get_active_entity_ids(limit)
        if normalized.startswith("select * from v_dashboard_stats"):
            return [self.get_dashboard_stats()]
        if normalized.startswith("select * from v_entity_summary where ubid = %s"):
            ubid = str(params[0]) if isinstance(params, tuple) and params else str(params)
            row = self.get_entity(ubid)
            return [row] if row else []
        if "count(*) as total" in normalized and "from entity_matches" in normalized:
            stats = self.get_match_stats()
            return [stats]
        return []

    def get_match_stats(self) -> dict:
        total = len(self.entity_matches)
        auto = len([m for m in self.entity_matches.values() if m.get("match_status") == "AUTO_LINKED"])
        review = len([m for m in self.entity_matches.values() if m.get("match_status") == "REVIEW"])
        merged = len([m for m in self.entity_matches.values() if m.get("match_status") == "MERGED"])
        rejected = len([m for m in self.entity_matches.values() if m.get("match_status") == "REJECTED"])
        avg_conf = round(sum(float(m.get("confidence", 0)) for m in self.entity_matches.values()) / max(total, 1), 3) if total else 0.0
        return {"total": total, "auto_linked": auto, "in_review": review, "merged": merged, "rejected": rejected, "avg_conf": avg_conf}

    def _entity_for_record(self, record_id: str) -> dict | None:
        link = self.record_links.get(record_id)
        if not link:
            return None
        return self.entities.get(link["ubid"])


_STORE: DemoStore | None = None


def get_store() -> DemoStore:
    global _STORE
    if _STORE is None:
        _STORE = DemoStore()
    return _STORE
