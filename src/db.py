# src/db.py
"""
Database layer — pipeline writes to PostgreSQL via SQLAlchemy.

Why SQLAlchemy not raw psycopg2?
- ORM-style API → portable across databases (SQLite for tests, Postgres for prod)
- Connection pooling baked in
- Pandas integration via to_sql / read_sql

Why PostgreSQL not SQLite?
- Production-grade: handles concurrent reads/writes, can scale to millions of rows
- For dev, we run it in Docker (zero install footprint when shut down)
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# Load .env from project root regardless of where script is run from
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def get_engine() -> Engine:
    """Returns a SQLAlchemy engine from DB_URL env var."""
    url = os.getenv("DB_URL")
    if not url:
        raise RuntimeError(
            "DB_URL not set. Check .env exists and contains DB_URL=postgresql://..."
        )
    return create_engine(url, pool_pre_ping=True)


def healthcheck() -> bool:
    """Quick test that DB is reachable. Used by run_full_pipeline."""
    from sqlalchemy import text
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"DB healthcheck failed: {e}")
        return False


if __name__ == "__main__":
    if healthcheck():
        print("✓ Database reachable")