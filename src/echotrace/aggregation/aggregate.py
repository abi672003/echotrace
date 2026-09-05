"""Cross-duplicate aggregation — EchoTrace's actual research contribution.

Combines per-copy AI-text-detector scores across a target article's
retrieved near-duplicate cluster, weighted by each copy's similarity to the
target. Adapted from QuAD (2026), a reliability-weighted quorum-aggregation
technique proven for image forensics, applied here to text for the first
time (per the brief — this is the one legitimate novelty claim; retrieval
and single-instance detection are both established baselines).

Not a trained model: a fixed, explainable formula, so every aggregated
verdict can cite exactly which evidence moved the score and by how much.
"""

from dataclasses import dataclass


@dataclass
class Evidence:
    id: str
    similarity: float
    score: float


@dataclass
class AggregationResult:
    aggregated_score: float
    single_instance_score: float
    evidence: list[Evidence]

    def to_dict(self) -> dict:
        return {
            "aggregated_score": self.aggregated_score,
            "single_instance_score": self.single_instance_score,
            "evidence": [e.__dict__ for e in self.evidence],
        }


def aggregate(target_score: float, duplicates: list[dict]) -> AggregationResult:
    """
    target_score: this article's own single-instance detector score.
    duplicates: [{id, text, similarity, score}, ...] from retrieval + detection.

    Reliability-weighted average: the target's own evidence always carries
    full weight (1.0); each duplicate's evidence is weighted by its
    similarity to the target, so a near-verbatim copy counts almost as much
    as the target itself while a loosely related "duplicate" barely moves
    the needle.
    """
    total_weight = 1.0
    weighted_sum = target_score * 1.0
    evidence = []

    for dup in duplicates:
        weight = max(0.0, dup["similarity"])
        weighted_sum += dup["score"] * weight
        total_weight += weight
        evidence.append(Evidence(id=dup["id"], similarity=dup["similarity"], score=dup["score"]))

    aggregated_score = weighted_sum / total_weight if total_weight > 0 else target_score

    return AggregationResult(
        aggregated_score=aggregated_score,
        single_instance_score=target_score,
        evidence=evidence,
    )
