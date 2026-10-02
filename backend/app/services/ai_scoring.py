import json

from sqlmodel import Session

from app.models import AiScoreCache
from app.services.llm import LLM

SYSTEM_PROMPT = (
    "You rate how much a public comment's writing style resembles AI-generated text. "
    "This is not a judgement about coordination, fraud, or authenticity -- using AI to "
    "write is legitimate; it is one weak, unverified signal among many. "
    'Reply with exactly one JSON object: {"scores": [{"id": <id>, "score": <0 to 1>, '
    '"reason": <one short phrase>}, ...]}, one entry per comment given, no prose, no '
    "code fences."
)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _build_user_message(items: list[tuple[str, str]]) -> str:
    payload = [{"id": text_hash, "text": text} for text_hash, text in items]
    return "Score these comments:\n" + json.dumps(payload)


async def score_members(
    session: Session, llm: LLM, items: list[tuple[str, str]]
) -> dict[str, tuple[float, str]]:
    """Batch-score up to `AI_SAMPLE_PER_FAMILY` (text_hash, text) pairs in one LLM call
    (medoid should be included by the caller), caching by `(text_hash, model)` in
    `AiScoreCache`. Returns `{text_hash: (score, reason)}`, score clamped to [0, 1]."""
    result: dict[str, tuple[float, str]] = {}
    to_score: dict[str, str] = {}

    for text_hash, text in items:
        if text_hash in result or text_hash in to_score:
            continue  # already resolved from cache or already queued this call
        cached = session.get(AiScoreCache, (text_hash, llm.model))
        if cached is not None:
            result[text_hash] = (cached.score, cached.reason)
        else:
            to_score[text_hash] = text

    if to_score:
        messages = [{"role": "user", "content": _build_user_message(list(to_score.items()))}]
        response = await llm.complete_json(SYSTEM_PROMPT, messages, schema={})
        scored_by_id = {str(item.get("id")): item for item in response.get("scores", [])}

        for text_hash in to_score:
            item = scored_by_id.get(text_hash)
            if item is None:
                score, reason = 0.0, "No score returned."
            else:
                try:
                    score = _clamp(float(item.get("score", 0.0)))
                except (TypeError, ValueError):
                    score = 0.0
                reason = str(item.get("reason", ""))
            result[text_hash] = (score, reason)
            session.add(
                AiScoreCache(text_hash=text_hash, model=llm.model, score=score, reason=reason)
            )
        session.commit()

    return result
