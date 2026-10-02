import pytest

from app.services.aggregation import family_ai_agg, single_comment_agg


def test_family_ai_agg_matches_hand_computed_value() -> None:
    # medoid (weight=1, its own similarity to itself) scored 0.5; two other scored
    # members with weight = similarity to medoid.
    scores = [0.5, 0.8, 0.6]
    weights = [1.0, 0.9, 0.7]
    # numerator = 0.5*1 + 0.8*0.9 + 0.6*0.7 = 0.5 + 0.72 + 0.42 = 1.64
    # denominator = 1.0 + 0.9 + 0.7 = 2.6
    expected = 1.64 / 2.6
    assert family_ai_agg(scores, weights) == pytest.approx(expected)


def test_family_ai_agg_single_medoid_only() -> None:
    assert family_ai_agg([0.42], [1.0]) == pytest.approx(0.42)


def test_family_ai_agg_empty_scores_is_zero() -> None:
    assert family_ai_agg([], []) == 0.0


def test_single_comment_agg_matches_hand_computed_value() -> None:
    target_score = 0.7
    neighbor_scores = [0.5, 0.9]
    neighbor_sims = [0.85, 0.9]
    # numerator = 0.7*1 + 0.5*0.85 + 0.9*0.9 = 0.7 + 0.425 + 0.81 = 1.935
    # denominator = 1 + 0.85 + 0.9 = 2.75
    expected = 1.935 / 2.75
    assert single_comment_agg(target_score, neighbor_scores, neighbor_sims) == pytest.approx(
        expected
    )


def test_single_comment_agg_no_neighbours_returns_target_score() -> None:
    assert single_comment_agg(0.6, [], []) == pytest.approx(0.6)
