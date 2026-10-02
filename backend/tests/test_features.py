import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.services.features import (
    CampaignMetrics,
    FamilyMember,
    campaign_score,
    compute_metrics,
    jaccard,
    preliminary_type,
    size_norm,
    word_shingles,
)

MIN_CAMPAIGN = 5


def _member(
    sim: float = 1.0,
    text: str = "this is a sample public comment about the proposed rule",
    text_hash: str = "h1",
    submitter_hash: str = "s1",
    is_anonymous: bool = False,
    posted_at: datetime | None = None,
) -> FamilyMember:
    return FamilyMember(
        sim_to_medoid=sim,
        text=text,
        text_hash=text_hash,
        submitter_hash=submitter_hash,
        is_anonymous=is_anonymous,
        posted_at=posted_at,
    )


# --- shingles / jaccard -----------------------------------------------------


def test_word_shingles_builds_3grams() -> None:
    shingles = word_shingles("the quick brown fox jumps")
    assert ("the", "quick", "brown") in shingles
    assert ("quick", "brown", "fox") in shingles
    assert ("brown", "fox", "jumps") in shingles
    assert len(shingles) == 3


def test_jaccard_identical_sets_is_one() -> None:
    a = word_shingles("the quick brown fox")
    assert jaccard(a, a) == 1.0


def test_jaccard_disjoint_sets_is_zero() -> None:
    a = word_shingles("alpha beta gamma")
    b = word_shingles("delta epsilon zeta")
    assert jaccard(a, b) == 0.0


def test_jaccard_both_empty_is_zero() -> None:
    assert jaccard(set(), set()) == 0.0


# --- compute_metrics ---------------------------------------------------------


def test_compute_metrics_basic_counts() -> None:
    medoid = _member(sim=1.0, text_hash="h1", submitter_hash="s1")
    members = [
        medoid,
        _member(sim=0.9, text_hash="h1", submitter_hash="s1"),  # exact dup, same submitter
        _member(sim=0.9, text_hash="h2", submitter_hash="s2", is_anonymous=True),
    ]
    metrics = compute_metrics(members, medoid, ai_agg=0.0)

    assert metrics.size == 3
    assert metrics.exact_dup_share == pytest.approx(2 / 3)  # h1 appears twice
    assert metrics.name_diversity == pytest.approx(2 / 3)  # s1, s1, s2 -> 2 distinct
    assert metrics.anon_share == pytest.approx(1 / 3)
    assert metrics.mean_sem == pytest.approx((1.0 + 0.9 + 0.9) / 3)


def test_compute_metrics_reword_index_formula() -> None:
    medoid = _member(sim=1.0, text="alpha beta gamma delta epsilon")
    other = _member(sim=0.8, text="alpha beta gamma delta epsilon")  # identical text
    members = [medoid, other]
    metrics = compute_metrics(members, medoid, ai_agg=0.0)
    assert metrics.mean_lex == pytest.approx(1.0)  # identical shingles both members
    assert metrics.reword_index == pytest.approx(metrics.mean_sem * (1 - metrics.mean_lex))
    assert metrics.reword_index == pytest.approx(0.0, abs=1e-9)


def test_compute_metrics_burst_24h_counts_tightest_window() -> None:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    medoid = _member(sim=1.0, posted_at=base)
    members = [
        medoid,
        _member(sim=0.9, posted_at=base + timedelta(hours=1)),
        _member(sim=0.9, posted_at=base + timedelta(hours=2)),
        _member(sim=0.9, posted_at=base + timedelta(days=10)),  # far outside any shared window
    ]
    metrics = compute_metrics(members, medoid, ai_agg=0.0)
    assert metrics.burst_24h == pytest.approx(3 / 4)  # 3 of 4 land in one 24h window


def test_compute_metrics_ai_agg_passes_through_unchanged() -> None:
    medoid = _member()
    metrics = compute_metrics([medoid], medoid, ai_agg=0.73)
    assert metrics.ai_agg == pytest.approx(0.73)


# --- size_norm / campaign_score -----------------------------------------------


def test_size_norm_caps_at_one() -> None:
    assert size_norm(50) == pytest.approx(1.0)
    assert size_norm(500) == pytest.approx(1.0)


def test_size_norm_matches_formula_for_small_n() -> None:
    import math

    assert size_norm(5) == pytest.approx(math.log(5) / math.log(50))


def test_campaign_score_matches_hand_computed_value() -> None:
    metrics = CampaignMetrics(
        size=5,
        mean_sem=0.9,
        mean_lex=0.2,
        reword_index=0.5,
        exact_dup_share=0.1,
        burst_24h=0.6,
        name_diversity=0.9,
        anon_share=0.0,
        ai_agg=0.7,
    )
    import math

    expected = 0.35 * (math.log(5) / math.log(50)) + 0.25 * 0.5 + 0.20 * 0.6 + 0.20 * 0.7
    assert campaign_score(metrics) == pytest.approx(expected)


# --- preliminary_type branches -------------------------------------------------


def _metrics(**overrides: float) -> CampaignMetrics:
    base = dict(
        size=5,
        mean_sem=0.9,
        mean_lex=0.1,
        reword_index=0.5,
        exact_dup_share=0.1,
        burst_24h=0.6,
        name_diversity=0.9,
        anon_share=0.0,
        ai_agg=0.0,
    )
    base.update(overrides)
    return CampaignMetrics(**base)


def test_type_form_letter_via_exact_dup_share() -> None:
    metrics = _metrics(exact_dup_share=0.6, reword_index=0.9, burst_24h=0.9, name_diversity=0.9)
    assert preliminary_type(metrics, MIN_CAMPAIGN) == "form_letter"


def test_type_form_letter_via_mean_lex() -> None:
    metrics = _metrics(mean_lex=0.65, exact_dup_share=0.0)
    assert preliminary_type(metrics, MIN_CAMPAIGN) == "form_letter"


def test_type_coordinated_paraphrase_campaign() -> None:
    metrics = _metrics(
        size=6, reword_index=0.5, burst_24h=0.6, name_diversity=0.2, mean_lex=0.1, exact_dup_share=0.1
    )
    assert preliminary_type(metrics, MIN_CAMPAIGN) == "coordinated_paraphrase_campaign"


def test_type_coordinated_paraphrase_campaign_via_name_diversity_instead_of_burst() -> None:
    metrics = _metrics(
        size=6, reword_index=0.5, burst_24h=0.1, name_diversity=0.85, mean_lex=0.1, exact_dup_share=0.1
    )
    assert preliminary_type(metrics, MIN_CAMPAIGN) == "coordinated_paraphrase_campaign"


def test_type_organic_agreement() -> None:
    metrics = _metrics(
        size=3, reword_index=0.5, burst_24h=0.1, name_diversity=0.9, mean_lex=0.1, exact_dup_share=0.0
    )
    assert preliminary_type(metrics, MIN_CAMPAIGN) == "organic_agreement"


def test_type_insufficient_evidence_default() -> None:
    metrics = _metrics(
        size=2, reword_index=0.1, burst_24h=0.1, name_diversity=0.1, mean_lex=0.1, exact_dup_share=0.0
    )
    assert preliminary_type(metrics, MIN_CAMPAIGN) == "insufficient_evidence"


# --- THE AI-ONLY GUARD (product-ethics rule, CLAUDE.md) -----------------------


def test_preliminary_type_has_no_ai_agg_parameter() -> None:
    """Structural guard: ai_agg isn't even an available variable in this function, so
    it is categorically impossible for an AI-style score to move a family into
    coordinated_paraphrase_campaign, by construction rather than by a conditional."""
    params = inspect.signature(preliminary_type).parameters
    assert "ai_agg" not in params


def test_ai_agg_alone_never_yields_campaign() -> None:
    """A maxed-out AI-style score with every other signal below the campaign
    thresholds must never classify as coordinated_paraphrase_campaign."""
    metrics = _metrics(
        size=2,  # below MIN_CAMPAIGN
        reword_index=0.1,  # below 0.45
        burst_24h=0.1,  # below 0.5
        name_diversity=0.1,  # below 0.8
        mean_lex=0.1,
        exact_dup_share=0.0,
        ai_agg=1.0,  # maximum possible AI-style signal
    )
    result = preliminary_type(metrics, MIN_CAMPAIGN)
    assert result != "coordinated_paraphrase_campaign"
    assert result == "insufficient_evidence"

    # campaign_score is still allowed to rise because of ai_agg...
    score_with_high_ai = campaign_score(metrics)
    score_with_low_ai = campaign_score(_metrics(**{**vars(metrics), "ai_agg": 0.0}))
    assert score_with_high_ai > score_with_low_ai
    # ...but the type verdict above proves that higher score never bought a campaign label.
