from __future__ import annotations

from datetime import datetime, date
import hashlib
import re
from typing import Any

from unidecode import unidecode


def clean_text(value: Any) -> str:
    text = unidecode(str(value or "")).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_pan(value: Any) -> str | None:
    pan = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    return pan if len(pan) == 10 else None


def normalize_gstin(value: Any) -> str | None:
    gstin = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    return gstin if len(gstin) == 15 else None


def normalize_pin(value: Any) -> str | None:
    pin = re.sub(r"[^0-9]", "", str(value or ""))
    return pin if len(pin) == 6 else None


def name_bucket(name: str) -> str:
    tokens = clean_text(name).split()
    if not tokens:
        return "unknown"
    return f"{tokens[0][:3]}:{tokens[-1][:3]}"


def record_hash(department_code: str, source_key: str, business_name: str) -> str:
    return hashlib.sha256(f"{department_code}::{source_key}::{business_name}".encode("utf-8")).hexdigest()


def to_date(value: Any) -> date | None:
    if value in (None, "", "null"):
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except Exception:
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except Exception:
            return None


def normalize_row(row: dict[str, Any], source_map: dict[str, str | None], department_code: str, source_key: str, row_number: int) -> tuple[dict, dict]:
    raw_payload = dict(row)
    business_name = str(row.get(source_map.get("business_name")) or "").strip()
    pan = normalize_pan(row.get(source_map.get("pan"))) if source_map.get("pan") else None
    gstin = normalize_gstin(row.get(source_map.get("gstin"))) if source_map.get("gstin") else None
    pin_code = normalize_pin(row.get(source_map.get("pin_code"))) if source_map.get("pin_code") else None
    district = str(row.get(source_map.get("district")) or "").strip() or None
    state = str(row.get(source_map.get("state")) or "").strip() or None
    city = str(row.get(source_map.get("city")) or "").strip() or None
    address_full = str(row.get(source_map.get("address_full")) or "").strip() or None
    sector = str(row.get(source_map.get("sector")) or "").strip() or None
    activity_date = to_date(row.get(source_map.get("activity_date"))) if source_map.get("activity_date") else None
    registration_date = to_date(row.get(source_map.get("registration_date"))) if source_map.get("registration_date") else None
    source_status = str(row.get(source_map.get("source_status")) or "").strip() or None
    record_key = f"{source_key}-{row_number}"
    return (
        {
            "source_row_number": row_number,
            "source_record_key": record_key,
            "department_code": department_code,
            "raw_payload": raw_payload,
            "raw_text": address_full or business_name,
            "ingestion_state": "NEW",
            "validation_errors": [],
            "mapping_warnings": [],
            "mapping_confidence": 100,
            "is_duplicate": False,
            "record_hash": record_hash(department_code, source_key, business_name or record_key),
            "business_name": business_name,
            "trade_name": business_name,
            "legal_name": business_name,
            "pan": pan,
            "gstin": gstin,
            "pin_code": pin_code,
            "district": district,
            "state": state,
            "city": city,
            "address_line1": address_full,
            "address_line2": None,
            "address_full": address_full,
            "activity_date": activity_date,
            "registration_date": registration_date,
            "last_activity_date": activity_date,
            "source_status": source_status,
            "source_category": None,
            "sector": sector,
            "extra_fields": {k: v for k, v in row.items() if k not in set(source_map.values())},
        },
        {
            "canonical_name": business_name or record_key,
            "canonical_name_key": clean_text(business_name or record_key),
            "name_tokens": clean_text(business_name or record_key).split(),
            "phonetic_key": clean_text(business_name or record_key)[:8],
            "name_bucket": name_bucket(business_name or record_key),
            "normalized_pan": pan,
            "normalized_gstin": gstin,
            "normalized_pin": pin_code,
            "normalized_district": district,
            "normalized_state": state,
            "normalized_city": city,
            "normalized_address": address_full,
            "address_key": clean_text(address_full or ""),
            "entity_type": "BUSINESS",
            "sector": sector,
            "confidence": 100,
            "source_flags": {},
            "feature_payload": {
                "department_code": department_code,
                "source_record_key": record_key,
            },
            "normalizer_version": "v1",
            "name_embedding": None,
            "record_hash": record_hash(department_code, source_key, business_name or record_key),
        },
    )
