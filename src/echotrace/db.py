"""SQLite schema and connection helper for EchoTrace's article/pair facts."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "db" / "echotrace.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id          TEXT PRIMARY KEY,
    text        TEXT NOT NULL,
    label       TEXT,
    cluster_id  INTEGER,
    source      TEXT NOT NULL,
    split       TEXT
);

CREATE TABLE IF NOT EXISTS duplicate_pairs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    article_a_id    TEXT NOT NULL REFERENCES articles(id),
    article_b_id    TEXT NOT NULL REFERENCES articles(id),
    label           TEXT NOT NULL,
    split           TEXT NOT NULL,
    source          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source);
CREATE INDEX IF NOT EXISTS idx_articles_cluster ON articles(cluster_id);
CREATE INDEX IF NOT EXISTS idx_pairs_split ON duplicate_pairs(split);
"""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn
