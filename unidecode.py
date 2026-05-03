"""Minimal unidecode-compatible helper."""

from __future__ import annotations

import unicodedata


def unidecode(text: str) -> str:
    if text is None:
        return ""
    normalized = unicodedata.normalize("NFKD", str(text))
    return normalized.encode("ascii", "ignore").decode("ascii")
