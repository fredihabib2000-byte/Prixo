"""PostgreSQL (Supabase) connection pool + helpers.

Every other module gets its connections from here:

    with get_conn() as conn:                # commits on success, rolls back on error
        row = conn.execute("SELECT ...", (x,)).fetchone()   # rows are dicts
"""
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from config import BASE_DIR, DATABASE_URL, DB_POOL_MAX, DB_POOL_MIN

_pool = None
_lock = threading.Lock()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                if not DATABASE_URL:
                    raise RuntimeError(
                        "DATABASE_URL is not set. Copy .env.example to .env and paste your "
                        "Supabase connection string (Project Settings -> Database)."
                    )
                pool = ConnectionPool(
                    conninfo=DATABASE_URL,
                    min_size=DB_POOL_MIN,
                    max_size=DB_POOL_MAX,
                    kwargs={
                        "row_factory": dict_row,
                        # Works with both Supabase poolers (session :5432 and transaction :6543)
                        "prepare_threshold": None,
                        "connect_timeout": 10,
                    },
                    check=ConnectionPool.check_connection,  # drop connections the server closed
                    open=False,
                )
                pool.open(wait=True, timeout=20)
                _pool = pool
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def get_conn():
    with get_pool().connection() as conn:
        yield conn


@contextmanager
def use_conn(conn=None):
    """Reuse `conn` if given (so several steps share one transaction), else open a new one."""
    if conn is not None:
        yield conn
    else:
        with get_conn() as c:
            yield c


def init_schema() -> None:
    """Create tables if they don't exist (idempotent, safe with several workers)."""
    with open(os.path.join(BASE_DIR, "schema.sql"), encoding="utf-8") as f:
        sql = f.read()
    with get_conn() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(724001)")  # serialize concurrent startups
        conn.execute(sql)
