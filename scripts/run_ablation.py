"""Ablation: aggregated vs. single-instance detection, bucketed by paraphrase
severity (embedding-similarity proxy). See docs/ABLATION_DESIGN.md for why
this measures false-positive reduction under real distribution shift rather
than true-positive lift — an honest limitation, not a shortcut.

Requires models/echotrace-detector/ (run notebooks/finetune_roberta_mdaigt.ipynb
first).
"""

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from echotrace.aggregation.aggregate import aggregate  # noqa: E402
from echotrace.db import get_connection  # noqa: E402
from echotrace.detection.detector import score_text  # noqa: E402
from echotrace.retrieval.search import find_near_duplicates  # noqa: E402

THRESHOLD = 0.5
TOP_K = 5

BUCKETS = [
    ("near-verbatim (sim >= 0.90)", 0.90, 1.01),
    ("moderate rewrite (0.75-0.90)", 0.75, 0.90),
    ("heavy rewrite (< 0.75)", 0.0, 0.75),
]


def bucket_for(similarity: float) -> str:
    for name, lo, hi in BUCKETS:
        if lo <= similarity < hi:
            return name
    return BUCKETS[-1][0]


def main():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, text, cluster_id FROM articles "
        "WHERE source = 'news-copy-eval-clusters' "
        "AND cluster_id IN (SELECT cluster_id FROM articles WHERE source='news-copy-eval-clusters' "
        "GROUP BY cluster_id HAVING COUNT(*) >= 2)"
    ).fetchall()
    conn.close()

    print(f"Evaluating {len(rows)} articles from real multi-member duplicate clusters "
          f"(ground truth: 100% human, per NEWS-COPY provenance)")

    bucket_results = defaultdict(lambda: {"n": 0, "single_fp": 0, "agg_fp": 0,
                                           "single_scores": [], "agg_scores": []})

    for i, (article_id, text, cluster_id) in enumerate(rows):
        single_score = score_text(text)
        duplicates_raw = find_near_duplicates(text, k=TOP_K, exclude_id=article_id)
        if not duplicates_raw:
            continue

        duplicates = [
            {"id": d["id"], "similarity": d["similarity"], "score": score_text(d["text"])}
            for d in duplicates_raw
        ]

        result = aggregate(single_score, duplicates)
        top_similarity = max(d["similarity"] for d in duplicates)
        bucket = bucket_for(top_similarity)

        b = bucket_results[bucket]
        b["n"] += 1
        b["single_fp"] += int(single_score > THRESHOLD)
        b["agg_fp"] += int(result.aggregated_score > THRESHOLD)
        b["single_scores"].append(single_score)
        b["agg_scores"].append(result.aggregated_score)

        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(rows)}")

    print("\n=== Ablation results (lower is better — true label is always 'human') ===")
    print(f"{'Bucket':<32} {'n':>5} {'single FP rate':>16} {'aggregated FP rate':>20} {'mean score drop':>16}")
    for name, _, _ in BUCKETS:
        b = bucket_results[name]
        if b["n"] == 0:
            print(f"{name:<32} {'(no examples)':>5}")
            continue
        single_fpr = b["single_fp"] / b["n"]
        agg_fpr = b["agg_fp"] / b["n"]
        mean_drop = (sum(b["single_scores"]) - sum(b["agg_scores"])) / b["n"]
        print(f"{name:<32} {b['n']:>5} {single_fpr:>16.3f} {agg_fpr:>20.3f} {mean_drop:>16.3f}")


if __name__ == "__main__":
    main()
