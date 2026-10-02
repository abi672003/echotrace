def family_ai_agg(scores: list[float], weights: list[float]) -> float:
    """§4.7 family mode: ai_agg = sum(s_i * w_i) / sum(w_i), where w_i is each scored
    member's similarity to the medoid (the medoid's own weight is 1, its similarity to
    itself). `scores`/`weights` cover only the members that were actually AI-scored."""
    if not scores:
        return 0.0
    numerator = sum(score * weight for score, weight in zip(scores, weights, strict=True))
    denominator = sum(weights)
    return numerator / denominator if denominator else 0.0


def single_comment_agg(
    target_score: float, neighbor_scores: list[float], neighbor_sims: list[float]
) -> float:
    """§4.7 single-comment mode: agg = (s_t*1 + sum(s_i*sim_i)) / (1 + sum(sim_i))."""
    numerator = target_score + sum(
        score * sim for score, sim in zip(neighbor_scores, neighbor_sims, strict=True)
    )
    denominator = 1 + sum(neighbor_sims)
    return numerator / denominator
