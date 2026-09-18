"""db.py tests — chiefly a regression test for a real bug found while
seeding a live deployment: a single bulk upsert_ignore() call over an
entire parquet file's worth of rows (tens of thousands of parameters)
blew past Postgres's 65535-per-statement parameter cap. Reproduced here
against SQLite (which has its own, lower cap) so it's caught by `pytest`
without needing a real Postgres instance."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select

from echotrace.db import articles, get_connection, reset_engine_for_tests, upsert_ignore


def test_upsert_ignore_handles_more_rows_than_one_statement_could_hold(tmp_path):
    reset_engine_for_tests(f"sqlite:///{(tmp_path / 'chunk_test.sqlite').as_posix()}")
    conn = get_connection()

    # 6 columns/row; a naive single INSERT of this many rows would need
    # ~120,000 bound parameters — well past both engines' per-statement caps.
    n = 20_000
    rows = [
        {"id": f"a{i}", "text": f"text {i}", "label": None, "cluster_id": None, "source": "test", "split": None}
        for i in range(n)
    ]

    upsert_ignore(conn, articles, rows)
    conn.commit()

    count = conn.execute(select(articles)).fetchall()
    conn.close()
    assert len(count) == n


def test_upsert_ignore_skips_existing_primary_keys(tmp_path):
    reset_engine_for_tests(f"sqlite:///{(tmp_path / 'ignore_test.sqlite').as_posix()}")
    conn = get_connection()

    upsert_ignore(conn, articles, [{"id": "dup", "text": "original", "label": None,
                                     "cluster_id": None, "source": "test", "split": None}])
    upsert_ignore(conn, articles, [{"id": "dup", "text": "should be ignored", "label": None,
                                     "cluster_id": None, "source": "test", "split": None}])
    conn.commit()

    row = conn.execute(select(articles).where(articles.c.id == "dup")).fetchone()
    conn.close()
    assert row.text == "original"
