"""Calibrate SIM_EDGE by printing max-neighbour-similarity histograms and resulting
family sizes for an already-ingested docket, at several candidate thresholds.

Usage (from backend/): python scripts\\calibrate.py <DOCKET_ID> [--thresholds 0.80 0.84 0.86 0.90]
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import engine  # noqa: E402
from app.models import Document, EmbeddingCache  # noqa: E402
from app.services.similarity import build_families, cosine_matrix  # noqa: E402

HISTOGRAM_BINS = [0.0, 0.5, 0.6, 0.7, 0.75, 0.80, 0.82, 0.84, 0.86, 0.88, 0.90, 0.95, 1.0]
DEFAULT_THRESHOLDS = [0.80, 0.82, 0.84, 0.86, 0.88, 0.90]


def load_docket_vectors(
    session: Session, docket_id: str, model: str
) -> tuple[list[int], np.ndarray]:
    documents = session.exec(select(Document).where(Document.docket_id == docket_id)).all()
    doc_ids: list[int] = []
    vectors: list[np.ndarray] = []
    for document in documents:
        cached = session.get(EmbeddingCache, (document.text_hash, model))
        if cached is None:
            continue
        doc_ids.append(document.id)
        vectors.append(np.frombuffer(cached.vector, dtype=np.float32))
    if not vectors:
        return doc_ids, np.zeros((0, 0), dtype=np.float32)
    return doc_ids, np.stack(vectors)


def max_neighbor_similarities(similarity: np.ndarray) -> list[float]:
    n = similarity.shape[0]
    result = []
    for i in range(n):
        others = [similarity[i, j] for j in range(n) if j != i]
        result.append(max(others) if others else 0.0)
    return result


def print_histogram(values: list[float], bins: list[float]) -> None:
    counts = [0] * (len(bins) - 1)
    for value in values:
        for i in range(len(bins) - 1):
            upper_inclusive = i == len(bins) - 2
            if bins[i] <= value < bins[i + 1] or (upper_inclusive and value == bins[-1]):
                counts[i] += 1
                break
    for i, count in enumerate(counts):
        print(f"  [{bins[i]:.2f}, {bins[i + 1]:.2f}): {count:4d} {'#' * count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate clustering thresholds for a docket.")
    parser.add_argument("docket_id")
    parser.add_argument("--thresholds", type=float, nargs="+", default=DEFAULT_THRESHOLDS)
    args = parser.parse_args()

    settings = get_settings()
    with Session(engine) as session:
        _, vectors = load_docket_vectors(session, args.docket_id, settings.GEMINI_EMBED_MODEL)

    if vectors.shape[0] < 2:
        print(f"Docket {args.docket_id!r} has fewer than 2 embedded documents; nothing to calibrate.")
        return 1

    similarity = cosine_matrix(vectors)
    print(f"Docket {args.docket_id}: {similarity.shape[0]} embedded documents")

    print("\nMax-neighbour similarity histogram:")
    print_histogram(max_neighbor_similarities(similarity), HISTOGRAM_BINS)

    print(f"\nFamily sizes per candidate SIM_EDGE (SIM_MEMBER={settings.SIM_MEMBER}, MIN_FAMILY={settings.MIN_FAMILY} held fixed):")
    for sim_edge in sorted(args.thresholds):
        families, _ = build_families(vectors, sim_edge, settings.SIM_MEMBER, settings.MIN_FAMILY)
        sizes = sorted((len(family.members) for family in families), reverse=True)
        print(f"  SIM_EDGE={sim_edge:.2f}: {len(families)} families, sizes={sizes}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
