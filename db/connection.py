from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator
import os

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError as exc:  # pragma: no cover - surfaced at runtime
    psycopg = None
    dict_row = None
    _IMPORT_ERROR = exc

from loguru import logger


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured.")
    return url


@contextmanager
def get_conn() -> Generator[Any, None, None]:
    if psycopg is None:
        raise ModuleNotFoundError(
            "A PostgreSQL driver is required. Install 'psycopg[binary]'."
        ) from _IMPORT_ERROR
    conn = psycopg.connect(_database_url(), sslmode=os.getenv("PGSSLMODE", "require"))
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_cursor() -> Generator[Any, None, None]:
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            yield cur


def execute(sql: str, params: tuple | dict | None = None) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(sql, params or None)
        if cur.description:
            rows = cur.fetchall()
            return [dict(row) for row in rows]
        return []


def execute_one(sql: str, params: tuple | dict | None = None) -> dict | None:
    rows = execute(sql, params)
    return rows[0] if rows else None


def execute_many(sql: str, params_list: list[tuple | dict]) -> int:
    if not params_list:
        return 0
    with get_cursor() as cur:
        cur.executemany(sql, params_list)
    return len(params_list)


def health_check() -> bool:
    try:
        row = execute_one("SELECT 1 AS ok")
        return bool(row and row.get("ok") == 1)
    except Exception as exc:  # pragma: no cover - surfaced in UI
        logger.warning("Database health check failed: {}", exc)
        return False


def init_schema() -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    schema_sql = schema_path.read_text(encoding="utf-8")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
    logger.info("Database schema initialized.")
