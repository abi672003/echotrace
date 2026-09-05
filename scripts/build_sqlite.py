"""Ingest real NEWS-COPY and M-DAIGT data into the SQLite data layer.

Sources and verification are documented in docs/DATA_PROVENANCE.md. This
script does not fabricate any data — it only reshapes the real downloaded
files into the schema defined in src/echotrace/db.py.
"""

import hashlib
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from echotrace.db import get_connection  # noqa: E402

RAW = ROOT / "data" / "raw"


def article_id(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def ingest_news_copy_pairs(conn):
    """train.parquet / dev.parquet: pairwise (Text 1, Text 2, Label, split)."""
    n_articles, n_pairs = 0, 0
    for fname in ["train.parquet", "dev.parquet"]:
        df = pd.read_parquet(RAW / "news-copy" / fname)
        for row in df.itertuples(index=False):
            id_a, id_b = article_id(row._0), article_id(row._1)
            for aid, text in [(id_a, row._0), (id_b, row._1)]:
                conn.execute(
                    "INSERT OR IGNORE INTO articles (id, text, label, cluster_id, source, split) "
                    "VALUES (?, ?, NULL, NULL, ?, ?)",
                    (aid, text, "news-copy-pairs", row.split),
                )
            conn.execute(
                "INSERT INTO duplicate_pairs (article_a_id, article_b_id, label, split, source) "
                "VALUES (?, ?, ?, ?, ?)",
                (id_a, id_b, row.Label, row.split, "news-copy-pairs"),
            )
            n_pairs += 1
        n_articles += len(df) * 2
    return n_articles, n_pairs


def ingest_news_copy_clusters(conn):
    """eval_val.parquet / eval_test.parquet: article-level rows with real cluster ids."""
    n = 0
    for fname, split in [("eval_val.parquet", "val"), ("eval_test.parquet", "test")]:
        df = pd.read_parquet(RAW / "news-copy" / fname)
        for row in df.itertuples(index=False):
            conn.execute(
                "INSERT OR IGNORE INTO articles (id, text, label, cluster_id, source, split) "
                "VALUES (?, ?, NULL, ?, ?, ?)",
                (row.id, row.article, int(row.cluster), "news-copy-eval-clusters", split),
            )
            n += 1
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
        for row in split_df.itertuples(index=False):
            aid = f"mdaigt-task1-{row.id}"
            conn.execute(
                "INSERT OR IGNORE INTO articles (id, text, label, cluster_id, source, split) "
                "VALUES (?, ?, ?, NULL, ?, ?)",
                (aid, row.text, row.label, "mdaigt-task1-news", split_name),
            )

    return {k: len(v) for k, v in splits.items()}


def main():
    conn = get_connection()

    n_articles, n_pairs = ingest_news_copy_pairs(conn)
    n_clusters = ingest_news_copy_clusters(conn)
    mdaigt_split_sizes = ingest_mdaigt_task1(conn)

    conn.commit()

    total_articles = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    total_pairs = conn.execute("SELECT COUNT(*) FROM duplicate_pairs").fetchone()[0]

    print("=== EchoTrace SQLite ingestion complete ===")
    print(f"NEWS-COPY pairwise rows processed: {n_pairs} pairs, ~{n_articles} article-sides")
    print(f"NEWS-COPY eval cluster articles ingested: {n_clusters}")
    print(f"M-DAIGT task1 (news) stratified split (seed=42): {mdaigt_split_sizes}")
    print(f"Total distinct articles in DB (deduped by content hash): {total_articles}")
    print(f"Total duplicate_pairs rows: {total_pairs}")

    conn.close()


if __name__ == "__main__":
    main()
