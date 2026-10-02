import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

_WORD_RE = re.compile(r"[a-z0-9']+")


@dataclass(frozen=True)
class FamilyMember:
    sim_to_medoid: float
    text: str
    text_hash: str
    submitter_hash: str
    is_anonymous: bool
    posted_at: datetime | None = None


@dataclass(frozen=True)
class CampaignMetrics:
    size: int
    mean_sem: float
    mean_lex: float
    reword_index: float
    exact_dup_share: float
    burst_24h: float
    name_diversity: float
    anon_share: float
    ai_agg: float


def word_shingles(text: str, n: int = 3) -> set[tuple[str, ...]]:
    words = _WORD_RE.findall(text.lower())
    if len(words) < n:
        return {tuple(words)} if words else set()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def jaccard(a: set, b: set) -> float:
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _max_24h_window_share(timestamps: list[datetime], n: int) -> float:
    if n == 0 or not timestamps:
        return 0.0
    sorted_times = sorted(timestamps)
    window = timedelta(hours=24)
    best = 0
    left = 0
    for right in range(len(sorted_times)):
        while sorted_times[right] - sorted_times[left] > window:
            left += 1
        best = max(best, right - left + 1)
    return best / n


def compute_metrics(
    members: list[FamilyMember], medoid: FamilyMember, ai_agg: float
) -> CampaignMetrics:
    """Campaign-shape features per §4.5. `members` includes the medoid itself (size = n
    counts it); `ai_agg` is the similarity-weighted AI-style score computed separately
    by `services/aggregation.py` (§4.7) — this function only ever *receives* it, it
    never derives it from raw per-member AI scores, keeping the AI-only guard (below)
    structurally enforced rather than merely incidental."""
    n = len(members)
    mean_sem = float(np.mean([m.sim_to_medoid for m in members]))

    medoid_shingles = word_shingles(medoid.text)
    mean_lex = float(np.mean([jaccard(word_shingles(m.text), medoid_shingles) for m in members]))

    reword_index = mean_sem * (1 - mean_lex)

    hash_counts: dict[str, int] = {}
    for m in members:
        hash_counts[m.text_hash] = hash_counts.get(m.text_hash, 0) + 1
    exact_dup_share = max(hash_counts.values()) / n

    burst_24h = _max_24h_window_share(
        [m.posted_at for m in members if m.posted_at is not None], n
    )

    name_diversity = len({m.submitter_hash for m in members}) / n
    anon_share = sum(1 for m in members if m.is_anonymous) / n

    return CampaignMetrics(
        size=n,
        mean_sem=mean_sem,
        mean_lex=mean_lex,
        reword_index=reword_index,
        exact_dup_share=exact_dup_share,
        burst_24h=burst_24h,
        name_diversity=name_diversity,
        anon_share=anon_share,
        ai_agg=ai_agg,
    )


def size_norm(n: int) -> float:
    return min(1.0, math.log(n) / math.log(50))


def campaign_score(metrics: CampaignMetrics) -> float:
    """§4.8. `ai_agg` contributes to the *score* only — see `preliminary_type` below."""
    return (
        0.35 * size_norm(metrics.size)
        + 0.25 * metrics.reword_index
        + 0.20 * metrics.burst_24h
        + 0.20 * metrics.ai_agg
    )


def preliminary_type(metrics: CampaignMetrics, min_campaign: int) -> str:
    """§4.8's rule-based type. DELIBERATE GUARD: this function's signature has no
    `ai_agg` parameter at all — an AI-style score can never, even accidentally, move a
    family into `coordinated_paraphrase_campaign`, because the information simply isn't
    available here to do so. See CLAUDE.md's product-ethics rule and the paired test
    `test_ai_agg_alone_never_yields_campaign`."""
    if metrics.exact_dup_share >= 0.5 or metrics.mean_lex >= 0.6:
        return "form_letter"
    if (
        metrics.size >= min_campaign
        and metrics.reword_index >= 0.45
        and (metrics.burst_24h >= 0.5 or metrics.name_diversity >= 0.8)
    ):
        return "coordinated_paraphrase_campaign"
    if metrics.reword_index >= 0.45 and metrics.burst_24h < 0.3:
        return "organic_agreement"
    return "insufficient_evidence"
