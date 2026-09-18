"""Ingest real NEWS-COPY and M-DAIGT data into the SQL data layer.

Sources and verification are documented in docs/DATA_PROVENANCE.md. This
script does not fabricate any data — it only reshapes the real downloaded
files into the schema defined in src/echotrace/db.py. Idempotent and
dialect-agnostic (SQLite for local dev, Postgres in Docker Compose) via
`echotrace.db.upsert_ignore` — safe to rerun.
"""

import hashlib
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text as sa_text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from echotrace.db import articles, duplicate_pairs, get_connection, upsert_ignore  # noqa: E402

RAW = ROOT / "data" / "raw"
CHUNK_SIZE = 500  # stay well under both engines' per-statement parameter caps


def _insert_chunked(conn, table, rows: list[dict]) -> None:
    for i in range(0, len(rows), CHUNK_SIZE):
        conn.execute(table.insert(), rows[i:i + CHUNK_SIZE])


def article_id(article_text: str) -> str:
    return hashlib.sha1(article_text.encode("utf-8")).hexdigest()


def ingest_news_copy_pairs(conn):
    """train.parquet / dev.parquet: pairwise (Text 1, Text 2, Label, split)."""
    n_articles, n_pairs = 0, 0
    for fname in ["train.parquet", "dev.parquet"]:
        df = pd.read_parquet(RAW / "news-copy" / fname)
        article_rows, pair_rows = [], []
        for row in df.itertuples(index=False):
            id_a, id_b = article_id(row._0), article_id(row._1)
            article_rows.append(
                {"id": id_a, "text": row._0, "label": None, "cluster_id": None,
                 "source": "news-copy-pairs", "split": row.split}
            )
            article_rows.append(
                {"id": id_b, "text": row._1, "label": None, "cluster_id": None,
                 "source": "news-copy-pairs", "split": row.split}
            )
            pair_rows.append(
                {"article_a_id": id_a, "article_b_id": id_b, "label": row.Label,
                 "split": row.split, "source": "news-copy-pairs"}
            )
        upsert_ignore(conn, articles, article_rows)
        _insert_chunked(conn, duplicate_pairs, pair_rows)
        n_pairs += len(pair_rows)
        n_articles += len(article_rows)
    return n_articles, n_pairs


def ingest_news_copy_clusters(conn):
    """eval_val.parquet / eval_test.parquet: article-level rows with real cluster ids."""
    n = 0
    for fname, split in [("eval_val.parquet", "val"), ("eval_test.parquet", "test")]:
        df = pd.read_parquet(RAW / "news-copy" / fname)
        rows = [
            {
                "id": row.id,
                "text": row.article,
                "label": None,
                "cluster_id": int(row.cluster),
                "source": "news-copy-eval-clusters",
                "split": split,
            }
            for row in df.itertuples(index=False)
        ]
        upsert_ignore(conn, articles, rows)
        n += len(rows)
    return n


def ingest_mdaigt_task1(conn, seed: int = 42):
    """train_mdaigt_task1.csv (News Article Detection, human/machine).

    No public official dev/test split is downloadable (CodaLab-gated, see
    docs/DATA_PROVENANCE.md) — create our own documented stratified 80/10/10
    split with a fixed seed.
    """
    df = pd.read_csv(RAW / "mdaigt" / "train_mdaigt_task1.csv")

    train_parts, val_parts, test_parts = [], [], []
    for label, group in df.groupby("label"):
        shuffled = group.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        n = len(shuffled)
        n_train = int(n * 0.8)
        n_val = int(n * 0.1)
        train_parts.append(shuffled.iloc[:n_train])
        val_parts.append(shuffled.iloc[n_train:n_train + n_val])
        test_parts.append(shuffled.iloc[n_train + n_val:])

    splits = {
        "train": pd.concat(train_parts, ignore_index=True),
        "val": pd.concat(val_parts, ignore_index=True),
        "test": pd.concat(test_parts, ignore_index=True),
    }

    for split_name, split_df in splits.items():
        rows = [
            {
                "id": f"mdaigt-task1-{row.id}",
                "text": row.text,
                "label": row.label,
                "cluster_id": None,
                "source": "mdaigt-task1-news",
                "split": split_name,
            }
            for row in split_df.itertuples(index=False)
        ]
        upsert_ignore(conn, articles, rows)

    return {k: len(v) for k, v in splits.items()}


def main():
    conn = get_connection()

    n_articles, n_pairs = ingest_news_copy_pairs(conn)
    n_clusters = ingest_news_copy_clusters(conn)
    mdaigt_split_sizes = ingest_mdaigt_task1(conn)

    conn.commit()

    total_articles = conn.execute(sa_text("SELECT COUNT(*) FROM articles")).fetchone()[0]
    total_pairs = conn.execute(sa_text("SELECT COUNT(*) FROM duplicate_pairs")).fetchone()[0]

    print("=== EchoTrace ingestion complete ===")
    print(f"NEWS-COPY pairwise rows processed: {n_pairs} pairs, ~{n_articles} article-sides")
    print(f"NEWS-COPY eval cluster articles ingested: {n_clusters}")
    print(f"M-DAIGT task1 (news) stratified split (seed=42): {mdaigt_split_sizes}")
    print(f"Total distinct articles in DB (deduped by content hash): {total_articles}")
    print(f"Total duplicate_pairs rows: {total_pairs}")

    conn.close()


if __name__ == "__main__":
    main()
