from __future__ import annotations

ALIASES = {
    "business_name": {"business_name", "name", "trade_name", "entity_name", "company_name"},
    "pan": {"pan", "pan_no", "pan_number"},
    "gstin": {"gstin", "gst_no", "gst_number", "gstin_number"},
    "pin_code": {"pin_code", "pincode", "pin", "postal_code", "zip"},
    "district": {"district", "dist"},
    "state": {"state", "province"},
    "city": {"city", "town"},
    "address_full": {"address_full", "address", "full_address", "registered_address", "location", "address_line1"},
    "activity_date": {"activity_date", "last_activity_date", "event_date"},
    "registration_date": {"registration_date", "reg_date", "incorporation_date"},
    "source_status": {"status", "source_status", "record_status"},
    "sector": {"sector", "industry", "line_of_business"},
}

CRITICAL_UPLOAD_FIELDS = [
    "business_name",
    "pan",
    "gstin",
    "pin_code",
    "city",
    "state",
    "address_full",
    "activity_date",
]


def guess_mapping(columns: list[str]) -> dict[str, str | None]:
    normalized = {str(col).strip().lower(): col for col in columns}
    mapping: dict[str, str | None] = {}
    for canonical, aliases in ALIASES.items():
        mapped = None
        for alias in aliases:
            if alias in normalized:
                mapped = normalized[alias]
                break
        mapping[canonical] = mapped
    return mapping


def validate_required(mapping: dict[str, str | None], required: list[str] | None = None) -> list[str]:
    required = required or ["business_name"]
    missing = [field for field in required if not mapping.get(field)]
    return missing
