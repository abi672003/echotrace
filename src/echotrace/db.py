"""SQLAlchemy engine, schema, and connection helper for EchoTrace's data layer.

Defaults to a local SQLite file for zero-setup dev; set DATABASE_URL (e.g. a
``postgresql+psycopg://...`` URL) to run against Postgres, as Docker Compose
does in production. Every query in this codebase uses SQLAlchemy Core
``text()`` with named parameters, so the same code runs unchanged against
either engine.

Call-site contract (unchanged from the old sqlite3-based version, so
existing call sites barely had to change): ``get_connection()`` returns a
live connection; the caller commits after writes and closes when done.
"""

import os
from pathlib import Path

from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy import text as sa_text
from sqlalchemy.engine import Connection, Engine

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = ROOT / "db" / "echotrace.sqlite"

metadata = MetaData()

articles = Table(
    "articles",
    metadata,
    Column("id", String, primary_key=True),
    Column("text", Text, nullable=False),
    Column("label", String),
    Column("cluster_id", Integer),
    Column("source", String, nullable=False),
    Column("split", String),
)

duplicate_pairs = Table(
    "duplicate_pairs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("article_a_id", String, nullable=False),
    Column("article_b_id", String, nullable=False),
    Column("label", String, nullable=False),
    Column("split", String, nullable=False),
    Column("source", String, nullable=False),
)

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String, nullable=False, unique=True),
    Column("password_hash", String, nullable=False),
    Column("created_at", String, nullable=False, server_default=sa_text("CURRENT_TIMESTAMP")),
)

# Live-retrieval cache: one row per successfully fetched+extracted URL, so
# re-investigating the same story doesn't re-scrape the same publisher.
fetched_articles = Table(
    "fetched_articles",
    metadata,
    Column("url", String, primary_key=True),
    Column("title", Text),
    Column("text", Text, nullable=False),
    Column("domain", String),
    Column("fetched_at", String, nullable=False, server_default=sa_text("CURRENT_TIMESTAMP")),
)

# One row per completed investigation, so a logged-in user has real history
# instead of a stateless demo.
investigations = Table(
    "investigations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("target_url", String),
    Column("target_text", Text, nullable=False),
    Column("verdict", String),
    Column("aggregated_score", Float),
    Column("single_instance_score", Float),
    Column("evidence_json", Text),
    Column("created_at", String, nullable=False, server_default=sa_text("CURRENT_TIMESTAMP")),
)


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = _database_url()
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        metadata.create_all(_engine)
    return _engine


def get_connection() -> Connection:
    """Live SQLAlchemy connection. Caller commits after writes, closes when done."""
    return get_engine().connect()


def upsert_ignore(conn: Connection, table: Table, rows: list[dict]) -> None:
    """Bulk-insert `rows`, silently skipping any whose primary key already
    exists — dialect-aware (SQLite / Postgres) so the same seeding code
    works against either engine without per-row existence checks."""
    if not rows:
        return
    dialect = conn.engine.dialect.name
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    elif dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    else:
        conn.execute(table.insert(), rows)
        return
    conn.execute(dialect_insert(table).values(rows).on_conflict_do_nothing())


def reset_engine_for_tests(url: str) -> Engine:
    """Test-only: force a fresh engine bound to `url` (e.g. an in-memory
    SQLite DB), bypassing the module-level cache."""
    global _engine
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    _engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    metadata.create_all(_engine)
    return _engine
