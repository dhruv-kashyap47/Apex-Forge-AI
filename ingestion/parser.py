from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd


def detect_file_format(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".csv"):
        return "CSV"
    if lower.endswith(".json"):
        return "JSON"
    raise ValueError("Unsupported file format. Expected CSV or JSON.")


def _parse_date_column(date_series: pd.Series) -> pd.Series:
    """Parse date column to UTC-aware datetime"""
    parsed_dates = []
    for date_val in date_series:
        if pd.isna(date_val) or date_val == "":
            parsed_dates.append(None)
            continue

        try:
            if isinstance(date_val, str):
                # Try ISO format first
                try:
                    dt = datetime.fromisoformat(date_val.replace('Z', '+00:00'))
                except ValueError:
                    # Try common formats
                    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%m-%d-%Y', '%Y/%m/%d', '%d/%m/%Y', '%m/%d/%Y'):
                        try:
                            dt = datetime.strptime(date_val, fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        print(f"Invalid date format: {date_val}")
                        parsed_dates.append(None)
                        continue

                # Ensure UTC timezone
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                parsed_dates.append(dt)
            else:
                # Already datetime, ensure UTC
                if date_val.tzinfo is None:
                    date_val = date_val.replace(tzinfo=timezone.utc)
                else:
                    date_val = date_val.astimezone(timezone.utc)
                parsed_dates.append(date_val)
        except Exception as e:
            print(f"Error parsing date '{date_val}': {e}")
            parsed_dates.append(None)

    return pd.Series(parsed_dates)


def parse_upload(file_obj: Any, filename: str) -> pd.DataFrame:
    file_format = detect_file_format(filename)
    raw = file_obj.getvalue()
    if file_format == "CSV":
        df = pd.read_csv(io.BytesIO(raw), on_bad_lines="skip")

        # Parse date columns if they exist
        date_columns = ['activity_date', 'registration_date', 'last_activity_date']
        for col in date_columns:
            if col in df.columns:
                df[col] = _parse_date_column(df[col])

        return df

    payload = json.loads(raw.decode("utf-8"))
    if isinstance(payload, dict):
        if "records" in payload and isinstance(payload["records"], list):
            payload = payload["records"]
        else:
            payload = [payload]
    return pd.DataFrame(payload)
