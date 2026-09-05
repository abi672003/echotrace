import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echotrace.aggregation.aggregate import aggregate


def test_no_duplicates_returns_single_instance_score():
    result = aggregate(target_score=0.8, duplicates=[])
    assert result.aggregated_score == 0.8
    assert result.single_instance_score == 0.8
    assert result.evidence == []


def test_high_similarity_duplicate_pulls_score_toward_it():
    # target scores high (looks AI-generated) but a near-verbatim duplicate
    # scores low (looks human) — aggregation should pull the verdict down
    # roughly proportional to how similar (trustworthy) that duplicate is.
    result = aggregate(target_score=0.9, duplicates=[{"id": "d1", "similarity": 0.99, "score": 0.1}])
    expected = (0.9 * 1.0 + 0.1 * 0.99) / (1.0 + 0.99)
    assert abs(result.aggregated_score - expected) < 1e-9
    assert result.aggregated_score < result.single_instance_score


def test_low_similarity_duplicate_barely_moves_score():
    result = aggregate(target_score=0.9, duplicates=[{"id": "d1", "similarity": 0.05, "score": 0.0}])
    assert result.aggregated_score > 0.85  # barely pulled down at all


def test_multiple_duplicates_all_counted():
    result = aggregate(
        target_score=0.5,
        duplicates=[
            {"id": "d1", "similarity": 0.9, "score": 1.0},
            {"id": "d2", "similarity": 0.9, "score": 0.0},
        ],
    )
    # symmetric evidence should roughly cancel out, staying near the target's own score
    assert abs(result.aggregated_score - 0.5) < 0.05
    assert len(result.evidence) == 2
