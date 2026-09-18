"""Embed the NEWS-COPY eval-cluster corpus into ChromaDB, linked to SQLite by id.

We embed the eval_val + eval_test cluster corpus (19,199 real articles with
ground-truth `cluster` labels) rather than the pairwise train/dev corpus,
because retrieval evaluation needs real cluster ground truth to measure
against — see docs/DATA_PROVENANCE.md.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import chromadb
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from echotrace.db import get_connection  # noqa: E402
from echotrace.retrieval.embed import embed_texts  # noqa: E402

CHROMA_DIR = ROOT / "db" / "chroma"
BATCH_SIZE = 256


def main():
    conn = get_connection()
    rows = conn.execute(
        text("SELECT id, text FROM articles WHERE source = 'news-copy-eval-clusters'")
    ).fetchall()
    conn.close()

    print(f"Embedding {len(rows)} articles with all-MiniLM-L6-v2 (local model)...")

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_or_create_collection(
        name="news_copy_articles",
        metadata={"hnsw:space": "cosine"},
    )

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        ids = [r[0] for r in batch]
        texts = [r[1] for r in batch]
        embeddings = embed_texts(texts)
        collection.add(ids=ids, embeddings=embeddings.tolist(), documents=texts)
        print(f"  {min(i + BATCH_SIZE, len(rows))}/{len(rows)}")

    print(f"Done. Collection count: {collection.count()}")


if __name__ == "__main__":
    main()
