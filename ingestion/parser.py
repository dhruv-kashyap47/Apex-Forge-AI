from __future__ import annotations

import io
import json
from typing import Any

import pandas as pd


def detect_file_format(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".csv"):
        return "CSV"
    if lower.endswith(".json"):
        return "JSON"
    raise ValueError("Unsupported file format. Expected CSV or JSON.")


def parse_upload(file_obj: Any, filename: str) -> pd.DataFrame:
    file_format = detect_file_format(filename)
    raw = file_obj.getvalue()
    if file_format == "CSV":
        return pd.read_csv(io.BytesIO(raw), on_bad_lines="skip")
    payload = json.loads(raw.decode("utf-8"))
    if isinstance(payload, dict):
        if "records" in payload and isinstance(payload["records"], list):
            payload = payload["records"]
        else:
            payload = [payload]
    return pd.DataFrame(payload)
