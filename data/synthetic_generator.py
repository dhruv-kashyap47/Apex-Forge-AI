"""
ApexForge AI — Synthetic Data Generator
Generates 10,000+ realistic Karnataka business records across:
  - 4 departments: GST, LABOUR, FACTORIES, KSPCB
  - 2 PIN codes: 560001 (Bengaluru Central), 560058 (Whitefield)

Design:
  - All records use SCRAMBLED/SYNTHETIC data — no real PII
  - ~30% of records represent the same real business appearing in multiple depts
    (these are the "ground truth" matches for the resolver to find)
  - Realistic Karnataka name/address/sector variations injected
  - Activity events generated to power the vitality engine
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from faker import Faker
from loguru import logger
from tqdm import tqdm
from unidecode import unidecode

from db.connection import init_schema, health_check, get_pool
from db import queries

fake = Faker("en_IN")
random.seed(42)

# ─── Config ───────────────────────────────────────────────────────────────────
TOTAL_BUSINESSES    = int(os.getenv("SEED_RECORDS", 2000))   # unique real businesses
PIN_CODES           = ["560001", "560058"]
DEPARTMENTS         = ["GST", "LABOUR", "FACTORIES", "KSPCB"]
MULTI_DEPT_RATIO    = 0.35   # 35% of businesses appear in 2+ departments
NOISE_RATIO         = 0.20   # 20% name/address noise injected (typos, abbreviations)

NOW = datetime.now(timezone.utc)

# ─── Karnataka Business Templates ─────────────────────────────────────────────

KA_NAME_PREFIXES = [
    "Shri", "Sri", "Smt", "M/s", "M/S", "Messrs",
    "Karnataka", "Mysore", "Bengaluru", "Karunadu", "Cauvery",
]

KA_BUSINESS_TYPES = [
    "Industries", "Enterprises", "Trade Link", "Exports", "Manufacturing",
    "Solutions", "Traders", "Firm", "Agency", "Works", "Mill", "Forge",
    "Tech", "Services", "International", "Pvt Ltd", "& Sons",
]

KA_SECTORS = [
    "Textiles", "Garments", "Chemicals", "Pharmaceuticals", "Electronics",
    "Auto Components", "Food Processing", "Plastics", "Metal Fabrication",
    "IT Services", "Printing", "Packaging", "Steel Works", "Electrical Equipment",
    "Beverages", "Granite & Stone", "Leather Goods", "Rubber Products",
]

KA_STREETS = [
    "MG Road", "Brigade Road", "Church Street", "Commercial Street",
    "Hosur Road", "Whitefield Main Road", "Old Madras Road",
    "Tumkur Road", "Mysore Road", "Bellary Road",
    "KIADB Industrial Area", "Peenya Industrial Estate",
    "Bommasandra Industrial Area", "Electronic City Phase",
    "Rajajinagar Industrial Area",
]

KA_SURNAMES = [
    "Reddy", "Gowda", "Naidu", "Shetty", "Hegde", "Patel", "Rao",
    "Murthy", "Iyer", "Iyengar", "Nair", "Pillai", "Sharma", "Kumar",
    "Rajan", "Krishnamurthy", "Venkatesh", "Subramaniam",
]

EVENT_TYPES_BY_DEPT = {
    "GST":       ["FILING", "RENEWAL", "INSPECTION"],
    "LABOUR":    ["INSPECTION", "RENEWAL", "COMPLAINT"],
    "FACTORIES": ["INSPECTION", "RENEWAL", "UTILITY", "SHUTDOWN"],
    "KSPCB":     ["INSPECTION", "RENEWAL", "COMPLAINT", "FILING"],
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _rand_pan() -> str:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    digits  = "0123456789"
    return (random.choice(letters) * 5 +
            "".join(random.choices(digits, k=4)) +
            random.choice(letters))


def _rand_gstin(pan: str, state: str = "29") -> str:
    """GSTIN = state_code(2) + PAN(10) + entity_no(1) + Z + checksum(1)"""
    entity_no = str(random.randint(1, 9))
    raw = f"{state}{pan}{entity_no}Z"
    checksum = random.choice("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return raw + checksum


def _generate_name() -> str:
    """Generate a realistic Karnataka business name."""
    parts = []
    if random.random() < 0.3:
        parts.append(random.choice(KA_NAME_PREFIXES))
    surname = random.choice(KA_SURNAMES)
    business_type = random.choice(KA_BUSINESS_TYPES)
    parts.append(surname)
    parts.append(business_type)
    return " ".join(parts)


def _inject_noise(name: str, noise_level: float = 0.3) -> str:
    """Simulate real-world data quality issues."""
    if random.random() > noise_level:
        return name

    choices = [
        lambda n: n.replace("Pvt Ltd", "P.Ltd").replace("Private Limited", "Pvt.Ltd"),
        lambda n: n.lower(),
        lambda n: n.upper(),
        lambda n: n.replace(" ", "  ").strip(),   # double space
        lambda n: n[:3] + "." + n[4:] if len(n) > 5 else n,  # partial abbrev
        lambda n: n.replace("Industries", "Inds").replace("Enterprises", "Ent"),
        lambda n: n.replace("Karnataka", "K'taka").replace("Bengaluru", "B'lore"),
        lambda n: unidecode(n) + " " + random.choice(["(Unit 1)", "(R)", "(Regd)"]),
    ]
    transform = random.choice(choices)
    return transform(name)


def _generate_address(pin: str) -> str:
    no   = random.randint(1, 999)
    street = random.choice(KA_STREETS)
    return f"No.{no}, {street}, Bengaluru - {pin}"


def _record_hash(dept: str, ext_id: str, name: str) -> str:
    raw = f"{dept}||{ext_id}||{name}".encode()
    return hashlib.sha256(raw).hexdigest()


def _random_date(start_days_ago: int, end_days_ago: int = 0) -> datetime:
    days = random.randint(end_days_ago, start_days_ago)
    return NOW - timedelta(days=days)


# ═══════════════════════════════════════════════════════════════════════════
# CORE BUSINESS GENERATOR
# ═══════════════════════════════════════════════════════════════════════════

def generate_business_master(n: int) -> list[dict]:
    """Generate n unique business master records (canonical ground truth)."""
    businesses = []
    for i in range(n):
        name   = _generate_name()
        pan    = _rand_pan() if random.random() < 0.75 else None
        gstin  = _rand_gstin(pan) if pan and random.random() < 0.80 else None
        pin    = random.choice(PIN_CODES)
        sector = random.choice(KA_SECTORS)
        reg_dt = _random_date(3650, 365)  # registered 1-10 years ago

        businesses.append({
            "master_id":           str(uuid.uuid4()),
            "canonical_name":      name,
            "pan":                 pan,
            "gstin":               gstin,
            "pin_code":            pin,
            "address":             _generate_address(pin),
            "sector":              sector,
            "registration_date":   reg_dt.date(),
            "vitality_profile":    _assign_vitality_profile(),
        })
    return businesses


def _assign_vitality_profile() -> str:
    """Assign a business lifecycle profile for realistic event generation."""
    r = random.random()
    if r < 0.55: return "active"
    if r < 0.75: return "dormant"
    if r < 0.88: return "recently_active"
    return "closed"


# ═══════════════════════════════════════════════════════════════════════════
# DEPARTMENT RECORD GENERATOR
# ═══════════════════════════════════════════════════════════════════════════

def generate_dept_records(businesses: list[dict]) -> list[dict]:
    """
    For each business, create 1-4 department records (with realistic noise).
    ~35% of businesses appear in multiple departments → ground-truth matches.
    """
    all_records: list[dict] = []

    for biz in businesses:
        # How many departments does this business appear in?
        is_multi = random.random() < MULTI_DEPT_RATIO
        if is_multi:
            num_depts = random.randint(2, 4)
            dept_list = random.sample(DEPARTMENTS, min(num_depts, 4))
        else:
            dept_list = [random.choice(DEPARTMENTS)]

        for dept in dept_list:
            ext_id  = f"{dept}-{random.randint(100000, 999999)}"
            # Inject realistic name variations
            noisy_name = _inject_noise(biz["canonical_name"], NOISE_RATIO)
            # Occasional PAN/GSTIN omissions (data quality issues)
            pan   = biz["pan"]   if random.random() > 0.15 else None
            gstin = biz["gstin"] if random.random() > 0.20 else None

            # Slight address variation
            address = _inject_noise(biz["address"], 0.25)

            rec = {
                "id":                str(uuid.uuid4()),
                "department_code":   dept,
                "external_id":       ext_id,
                "business_name":     noisy_name,
                "normalized_name":   noisy_name.lower().strip(),
                "pan":               pan,
                "gstin":             gstin,
                "address":           address,
                "pin_code":          biz["pin_code"],
                "sector":            biz["sector"],
                "phone":             fake.phone_number()[:15],
                "email":             None,   # PII omitted per non-negotiable
                "registration_date": biz["registration_date"],
                "status_raw":        _dept_status(dept, biz["vitality_profile"]),
                "extra_data":        json.dumps(_dept_extra(dept)),
                "record_hash":       _record_hash(dept, ext_id, noisy_name),
                # Metadata for post-processing
                "_master_id":        biz["master_id"],
                "_vitality_profile": biz["vitality_profile"],
            }
            all_records.append(rec)

    return all_records


def _dept_status(dept: str, profile: str) -> str:
    status_map = {
        "active":         {"GST": "Active", "LABOUR": "Valid",
                           "FACTORIES": "Operating", "KSPCB": "Consent Valid"},
        "dormant":        {"GST": "Inactive", "LABOUR": "Suspended",
                           "FACTORIES": "Idle",      "KSPCB": "Consent Expired"},
        "recently_active":{"GST": "Active", "LABOUR": "Valid",
                           "FACTORIES": "Operating", "KSPCB": "Under Renewal"},
        "closed":         {"GST": "Cancelled", "LABOUR": "Closed",
                           "FACTORIES": "Surrendered","KSPCB": "Consent Revoked"},
    }
    return status_map.get(profile, {}).get(dept, "Unknown")


def _dept_extra(dept: str) -> dict:
    """Dept-specific fields stored in JSONB."""
    if dept == "GST":
        return {"gst_category": random.choice(["Regular", "Composition", "TDS"]),
                "turnover_band": random.choice(["<40L", "40L-1.5Cr", ">1.5Cr"])}
    if dept == "LABOUR":
        return {"employees": random.randint(5, 500),
                "contract_workers": random.randint(0, 50)}
    if dept == "FACTORIES":
        return {"power_kw": random.randint(10, 5000),
                "category": random.choice(["Small", "Medium", "Large"])}
    if dept == "KSPCB":
        return {"consent_type": random.choice(["Orange", "Red", "Green"]),
                "effluent_volume_kld": random.randint(0, 200)}
    return {}


# ═══════════════════════════════════════════════════════════════════════════
# ACTIVITY EVENT GENERATOR
# ═══════════════════════════════════════════════════════════════════════════

def generate_events(records: list[dict]) -> list[dict]:
    """
    Generate temporal activity events per record based on vitality profile.
    These power the vitality engine.
    """
    events: list[dict] = []

    for rec in records:
        profile = rec.get("_vitality_profile", "dormant")
        dept    = rec["department_code"]
        event_types = EVENT_TYPES_BY_DEPT.get(dept, ["INSPECTION"])

        schedule = {
            "active":          {"count": (4, 12), "max_days_ago":  365},
            "recently_active": {"count": (2,  6), "max_days_ago":  540},
            "dormant":         {"count": (0,  3), "max_days_ago": 1095},
            "closed":          {"count": (0,  2), "max_days_ago": 1800},
        }.get(profile, {"count": (0, 2), "max_days_ago": 900})

        count = random.randint(*schedule["count"])
        for _ in range(count):
            etype = random.choice(event_types)
            # Closed businesses: add shutdown event
            if profile == "closed" and random.random() < 0.6:
                etype = "SHUTDOWN"
            edate = _random_date(schedule["max_days_ago"])
            events.append({
                "raw_record_id":   rec["id"],
                "department_code": dept,
                "event_type":      etype,
                "event_date":      edate,
                "signal_strength": EVENT_WEIGHTS_SEED.get(etype, 0.5),
                "details":         json.dumps({"source": dept, "auto_generated": True}),
                "ubid":            None,  # filled after entity creation
            })

    return events


EVENT_WEIGHTS_SEED = {
    "RENEWAL": 1.0, "INSPECTION": 0.9, "FILING": 0.8,
    "UTILITY": 0.7, "COMPLAINT": 0.3, "SHUTDOWN": 0.1,
}


# ═══════════════════════════════════════════════════════════════════════════
# SEEDING ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════

def run_seed() -> None:
    """
    Full seed pipeline:
      1. Init schema
      2. Generate businesses + department records
      3. Compute & store embeddings (batch)
      4. Insert records + events
      5. Run initial entity resolution
      6. Run vitality classification
    """
    logger.info("━" * 60)
    logger.info("ApexForge AI — Synthetic Data Seeder")
    logger.info("━" * 60)

    # ── Wait for DB ───────────────────────────────────────────────────────
    for attempt in range(10):
        if health_check():
            break
        logger.info(f"Waiting for PostgreSQL… ({attempt+1}/10)")
        import time; time.sleep(3)
    else:
        logger.error("Could not connect to PostgreSQL. Exiting.")
        sys.exit(1)

    # ── Init schema ───────────────────────────────────────────────────────
    init_schema()
    logger.info("Schema initialised.")

    # ── Check if already seeded ───────────────────────────────────────────
    existing = queries.execute_one("SELECT COUNT(*) AS n FROM raw_records")
    if existing and existing["n"] > 100:
        logger.info(f"Database already has {existing['n']} records — skipping seed.")
        return

    logger.info(f"Generating {TOTAL_BUSINESSES} businesses…")
    businesses = generate_business_master(TOTAL_BUSINESSES)

    logger.info("Generating department records with noise injection…")
    records = generate_dept_records(businesses)
    logger.info(f"  → {len(records)} total department records across {len(DEPARTMENTS)} departments")

    # ── Compute embeddings first ──────────────────────────────────────────
    logger.info("Computing embeddings (this runs locally)…")
    from models.embedding_model import get_model, EmbeddingModel
    model = get_model()
    texts = [EmbeddingModel.build_record_text(r) for r in records]
    embeddings = model.encode_batch(texts, batch_size=128)
    for rec, emb in zip(records, embeddings):
        rec["_embedding"] = emb

    # ── Insert raw_records ────────────────────────────────────────────────
    logger.info("Inserting raw records into PostgreSQL…")
    for rec in tqdm(records, desc="Inserting records"):
        clean = {k: v for k, v in rec.items() if not k.startswith("_")}
        try:
            rid = queries.upsert_raw_record(clean)
            # Store embedding
            queries.update_record_embedding(str(rid), rec["_embedding"])
        except Exception as e:
            logger.warning(f"Skipping record {rec.get('id')}: {e}")

    logger.info("Records inserted.")

    # ── Generate & insert activity events ─────────────────────────────────
    logger.info("Generating activity events…")
    events = generate_events(records)
    logger.info(f"  → {len(events)} events generated")

    for ev in tqdm(events, desc="Inserting events"):
        try:
            queries.insert_event({
                "ubid":            None,
                "raw_record_id":   ev["raw_record_id"],
                "department_code": ev["department_code"],
                "event_type":      ev["event_type"],
                "event_date":      ev["event_date"],
                "signal_strength": ev["signal_strength"],
                "details":         ev["details"],
            })
        except Exception as e:
            logger.warning(f"Event insert error: {e}")

    logger.info("Events inserted.")

    # ── Run entity resolution ─────────────────────────────────────────────
    logger.info("Running initial entity resolution pipeline…")
    from engine.resolver import run_resolution
    stats = run_resolution()
    logger.info(f"Resolution stats: {stats}")

    # ── Run vitality classification ───────────────────────────────────────
    logger.info("Running vitality classification…")
    from engine.vitality import classify_all_entities
    v_stats = classify_all_entities()
    logger.info(f"Vitality stats: {v_stats}")

    logger.info("━" * 60)
    logger.info("✅  Seed complete! ApexForge AI is ready.")
    logger.info(f"    Records:   {len(records)}")
    logger.info(f"    Events:    {len(events)}")
    logger.info(f"    Dashboard: http://localhost:8501")
    logger.info("━" * 60)


if __name__ == "__main__":
    run_seed()
