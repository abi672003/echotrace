import numpy as np
import pytest
import respx
from httpx import Response
from sqlmodel import Session, SQLModel, create_engine

from app.services.embeddings import GEMINI_BASE_URL, FakeEmbedder, GeminiEmbedder, embed_texts


@pytest.mark.asyncio
async def test_vectors_are_l2_normalised() -> None:
    embedder = FakeEmbedder()
    vectors = await embedder.embed_raw(["hello world", "goodbye world"])
    for vector in vectors:
        assert np.isclose(np.linalg.norm(vector), 1.0, atol=1e-5)


@pytest.mark.asyncio
async def test_same_text_hash_yields_same_vector_deterministically() -> None:
    embedder = FakeEmbedder()
    a = (await embedder.embed_raw(["hello world"]))[0]
    b = (await embedder.embed_raw(["hello world"]))[0]
    assert np.array_equal(a, b)


@pytest.mark.asyncio
async def test_embedding_the_sample_twice_makes_zero_api_calls_the_second_time() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    embedder = FakeEmbedder()
    texts = {"hash1": "hello world", "hash2": "goodbye world", "hash3": "a third comment"}

    with Session(engine) as session:
        first = await embed_texts(session, embedder, texts)
        assert embedder.call_count == 1
        assert set(first.keys()) == set(texts.keys())

        second = await embed_texts(session, embedder, texts)
        assert embedder.call_count == 1  # zero additional API calls

        for text_hash in texts:
            assert np.array_equal(first[text_hash], second[text_hash])


@pytest.mark.asyncio
async def test_embed_texts_only_calls_embedder_for_uncached_hashes() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    embedder = FakeEmbedder()

    with Session(engine) as session:
        await embed_texts(session, embedder, {"hash1": "hello world"})
        assert embedder.call_count == 1

        result = await embed_texts(
            session, embedder, {"hash1": "hello world", "hash2": "new comment"}
        )
        assert embedder.call_count == 2  # only the new hash triggered a call
        assert set(result.keys()) == {"hash1", "hash2"}


@pytest.mark.asyncio
@respx.mock
async def test_gemini_embedder_tracks_call_count() -> None:
    """GeminiEmbedder previously had no call_count at all, so Analysis.embed_calls
    silently read 0 for every real run regardless of actual API usage (caught running
    the real pipeline end to end, Task 3.14) - this is the regression guard."""
    respx.post(f"{GEMINI_BASE_URL}/v1beta/models/gemini-embedding-001:batchEmbedContents").mock(
        return_value=Response(200, json={"embeddings": [{"values": [1.0, 0.0]}]})
    )
    embedder = GeminiEmbedder()
    assert embedder.call_count == 0
    await embedder.embed_raw(["one comment"])
    assert embedder.call_count == 1
    await embedder.embed_raw(["another comment"])
    assert embedder.call_count == 2
    await embedder.aclose()
