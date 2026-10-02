import numpy as np
from sqlmodel import Session, SQLModel, create_engine

from app.models import EmbeddingCache
from app.services.compare import lexical_similarity, semantic_similarity, shared_spans

MODEL = "gemini-embedding-001"


def test_shared_spans_finds_a_long_shared_run() -> None:
    text_a = "I am writing to express my strong opposition to this proposed rule today."
    text_b = "As a resident, I am writing to express my strong opposition to this rule."

    spans = shared_spans(text_a, text_b, min_words=5)

    assert len(spans) >= 1
    span = spans[0]
    shared_text = text_a[span["a_start"] : span["a_end"]].lower()
    assert "writing to express my strong opposition" in shared_text
    assert text_b[span["b_start"] : span["b_end"]].lower() == shared_text


def test_shared_spans_ignores_short_matches_below_min_words() -> None:
    text_a = "The quick brown fox jumps over the lazy dog."
    text_b = "A completely different sentence with the lazy dog mentioned once."
    # only "the lazy dog" (3 words) overlaps - below the 5-word floor
    spans = shared_spans(text_a, text_b, min_words=5)
    assert spans == []


def test_shared_spans_no_overlap_returns_empty() -> None:
    spans = shared_spans("alpha beta gamma delta epsilon", "zeta eta theta iota kappa")
    assert spans == []


def test_lexical_similarity_identical_texts_is_one() -> None:
    text = "this is a sample public comment about the proposed rule change"
    assert lexical_similarity(text, text) == 1.0


def test_lexical_similarity_unrelated_texts_is_low() -> None:
    a = "I strongly oppose this environmental regulation change"
    b = "The quarterly financial report shows increased revenue"
    assert lexical_similarity(a, b) < 0.2


def test_semantic_similarity_uses_cached_embeddings() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    vec_a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    vec_b = np.array([0.0, 1.0, 0.0], dtype=np.float32)

    with Session(engine) as session:
        session.add(EmbeddingCache(text_hash="ha", model=MODEL, dim=3, vector=vec_a.tobytes()))
        session.add(EmbeddingCache(text_hash="hb", model=MODEL, dim=3, vector=vec_b.tobytes()))
        session.commit()

        assert semantic_similarity(session, MODEL, "ha", "hb") == 0.0
        assert semantic_similarity(session, MODEL, "ha", "ha") == 1.0


def test_semantic_similarity_defaults_to_zero_when_uncached() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        assert semantic_similarity(session, MODEL, "missing-a", "missing-b") == 0.0
