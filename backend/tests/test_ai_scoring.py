import json

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.services.ai_scoring import score_members
from app.services.llm import FakeLLM


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.mark.asyncio
async def test_score_members_returns_clamped_scores_in_one_batched_call() -> None:
    llm = FakeLLM(
        [
            json.dumps(
                {
                    "scores": [
                        {"id": "h1", "score": 0.9, "reason": "formal tone"},
                        {"id": "h2", "score": 1.5, "reason": "over 1, should clamp"},
                        {"id": "h3", "score": -0.2, "reason": "under 0, should clamp"},
                    ]
                }
            )
        ]
    )
    items = [("h1", "text one"), ("h2", "text two"), ("h3", "text three")]

    with Session(_engine()) as session:
        result = await score_members(session, llm, items)

    assert llm.call_count == 1  # one batched call, not one per comment
    assert result["h1"] == (0.9, "formal tone")
    assert result["h2"][0] == 1.0  # clamped down
    assert result["h3"][0] == 0.0  # clamped up


@pytest.mark.asyncio
async def test_score_members_defaults_missing_id_to_zero() -> None:
    llm = FakeLLM([json.dumps({"scores": [{"id": "h1", "score": 0.5, "reason": "ok"}]})])
    items = [("h1", "text one"), ("h2", "text two — model forgot to score this one")]

    with Session(_engine()) as session:
        result = await score_members(session, llm, items)

    assert result["h1"] == (0.5, "ok")
    assert result["h2"] == (0.0, "No score returned.")


@pytest.mark.asyncio
async def test_score_members_caches_and_skips_already_scored_hashes() -> None:
    llm = FakeLLM(
        [
            json.dumps({"scores": [{"id": "h1", "score": 0.7, "reason": "first run"}]}),
            json.dumps({"scores": [{"id": "h2", "score": 0.3, "reason": "second run"}]}),
        ]
    )
    engine = _engine()

    with Session(engine) as session:
        first = await score_members(session, llm, [("h1", "text one")])
        assert llm.call_count == 1
        assert first["h1"] == (0.7, "first run")

        # h1 is already cached; only h2 should trigger a new LLM call
        second = await score_members(session, llm, [("h1", "text one"), ("h2", "text two")])
        assert llm.call_count == 2
        assert second["h1"] == (0.7, "first run")  # from cache, unchanged
        assert second["h2"] == (0.3, "second run")


@pytest.mark.asyncio
async def test_score_members_makes_no_call_when_everything_is_cached() -> None:
    llm = FakeLLM([json.dumps({"scores": [{"id": "h1", "score": 0.4, "reason": "cached"}]})])
    engine = _engine()

    with Session(engine) as session:
        await score_members(session, llm, [("h1", "text one")])
        assert llm.call_count == 1

        result = await score_members(session, llm, [("h1", "text one")])
        assert llm.call_count == 1  # no new call
        assert result["h1"] == (0.4, "cached")
