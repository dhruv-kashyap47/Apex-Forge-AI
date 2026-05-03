"""Minimal python-dotenv compatible shim used by the app.

This keeps the project runnable when the external dependency is absent.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _parse_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[7:].lstrip()
    if "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip().strip("'").strip('"')
    return key, value


def load_dotenv(dotenv_path: str | os.PathLike[str] | None = None, override: bool = False, **_: Any) -> bool:
    """Load environment variables from a .env file.

    Only the subset used by this repository is implemented.
    """

    path = Path(dotenv_path or ".env")
    if path.is_dir():
        path = path / ".env"
    if not path.exists():
        return False

    loaded = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_line(raw_line)
        if not parsed:
            continue
        key, value = parsed
        if override or key not in os.environ:
            os.environ[key] = value
        loaded = True
    return loaded
