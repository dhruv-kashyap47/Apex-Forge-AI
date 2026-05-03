"""
ApexForge AI — Database Connection Manager

This repository ships with a self-contained demo datastore so the Streamlit
application can run without PostgreSQL or extra binary dependencies.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator

from loguru import logger

from db.demo_store import get_store


class _DemoCursor:
    def __init__(self) -> None:
        self._rows: list[dict] = []
        self.description = None

    def execute(self, sql: str, params: tuple | dict | None = None) -> None:
        self._rows = get_store().execute_sql(sql, params)
        self.description = [("demo",)] if self._rows else None

    def fetchall(self) -> list[dict]:
        return self._rows

    def fetchone(self) -> dict | None:
        return self._rows[0] if self._rows else None

    def __enter__(self) -> "_DemoCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _DemoConnection:
    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def cursor(self) -> _DemoCursor:
        return _DemoCursor()


class _DemoPool:
    closed = False

    def getconn(self) -> _DemoConnection:
        return _DemoConnection()

    def putconn(self, conn: _DemoConnection) -> None:
        return None


_pool = _DemoPool()


def get_pool(min_conn: int = 2, max_conn: int = 10) -> _DemoPool:
    """Return the in-memory demo pool."""
    logger.info("Using in-memory demo datastore.")
    return _pool


@contextmanager
def get_conn() -> Generator[_DemoConnection, None, None]:
    """Yield a demo connection."""
    conn = _DemoConnection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


@contextmanager
def get_cursor() -> Generator[_DemoCursor, None, None]:
    """Yield a demo cursor."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            yield cur


def execute(sql: str, params: tuple | dict | None = None) -> list[dict]:
    return get_store().execute_sql(sql, params)


def execute_one(sql: str, params: tuple | dict | None = None) -> dict | None:
    rows = execute(sql, params)
    return rows[0] if rows else None


def execute_many(sql: str, params_list: list[tuple | dict]) -> int:
    count = 0
    for params in params_list:
        execute(sql, params)
        count += 1
    return count


def health_check() -> bool:
    return get_store().health_check()


def init_schema() -> None:
    logger.info("Demo datastore active; no schema migration required.")

