"""Sync the local SQLite `split` column for M-DAIGT articles to match the
exact train/val/test split a Colab training run actually used.

build_sqlite.py derives this split locally by re-running the same seeded
`group.sample(random_state=42)` logic the training notebook uses — but that
independent re-derivation can silently diverge from what the notebook
actually did, because pandas/numpy sampling isn't guaranteed identical
across the two separate Python environments even with the same seed and
same input data. The training notebook now exports the split it actually
used (mdaigt_task1_splits.csv, bundled into the model export); this script
makes the local demo data agree with that ground truth instead of hoping
the two environments agreed.

Usage:
    python3 scripts/apply_mdaigt_split.py models/echotrace-detector/mdaigt_task1_splits.csv
"""

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from echotrace.db import get_connection  # noqa: E402


def main(csv_path: str) -> None:
    manifest = pd.read_csv(csv_path)
    conn = get_connection()

    updated = 0
    missing = 0
    for row in manifest.itertuples(index=False):
        aid = f"mdaigt-task1-{row.id}"
        cur = conn.execute(
            text("UPDATE articles SET split = :split WHERE id = :id AND source = 'mdaigt-task1-news'"),
            {"split": row.split, "id": aid},
        )
        if cur.rowcount == 0:
            missing += 1
        else:
            updated += 1
    conn.commit()

    counts = conn.execute(
        text("SELECT split, COUNT(*) FROM articles WHERE source = 'mdaigt-task1-news' GROUP BY split")
    ).fetchall()
    conn.close()

    print(f"Updated {updated} rows, {missing} manifest ids not found locally.")
    print("Local split counts now:", dict(counts))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
