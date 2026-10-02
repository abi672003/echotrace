import hashlib
from typing import Protocol

import httpx
import numpy as np
from sqlmodel import Session

from app.config import get_settings
from app.models import EmbeddingCache
from app.services.ratelimit import get_bucket, with_retries

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com"
# ARCHITECTURE §4.3 says "up to 100 per request," but the free tier's real embedding
# quota is token-volume-based, not just request-count-based: measured against this
# project's real public-comment text, a 100-comment batch (~185K chars) reliably hit
# 429 RESOURCE_EXHAUSTED, a 30-comment batch (~64K chars) reliably succeeded, and a
# 40-comment batch (~82K chars) reliably failed (see docs/NOTES.md, Task 3.14). 20
# keeps a safety margin below that measured boundary for longer-than-average comments.
GEMINI_BATCH_SIZE = 20
# httpx defaults to a 5s timeout, too short for a real embedding batch call.
EMBED_HTTP_TIMEOUT = 60.0


class Embedder(Protocol):
    model: str

    async def embed_raw(self, texts: list[str]) -> list[np.ndarray]:
        """Embed raw texts (same order), returning L2-normalised float32 vectors."""
        ...


def _l2_normalise(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    return vector / norm if norm > 0 else vector


def _vector_to_bytes(vector: np.ndarray) -> bytes:
    return vector.astype(np.float32).tobytes()


def _bytes_to_vector(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float32)


class GeminiEmbedder:
    """Embedder protocol for Gemini embeddings (§4.3): batches of <=100, task type
    CLUSTERING, output dimensionality from settings, L2-normalised."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        settings = get_settings()
        self.model = settings.GEMINI_EMBED_MODEL
        self.call_count = 0
        self._dim = settings.GEMINI_EMBED_DIM
        self._api_key = settings.GEMINI_API_KEY.get_secret_value()
        self._client = client or httpx.AsyncClient(base_url=GEMINI_BASE_URL, timeout=EMBED_HTTP_TIMEOUT)
        self._bucket = get_bucket("gemini")

    async def aclose(self) -> None:
        await self._client.aclose()

    async def embed_raw(self, texts: list[str]) -> list[np.ndarray]:
        vectors: list[np.ndarray] = []
        for start in range(0, len(texts), GEMINI_BATCH_SIZE):
            batch = texts[start : start + GEMINI_BATCH_SIZE]
            vectors.extend(await self._embed_one_batch(batch))
        return vectors

    async def _embed_one_batch(self, batch: list[str]) -> list[np.ndarray]:
        await self._bucket.acquire()
        self.call_count += 1

        async def _request() -> httpx.Response:
            return await self._client.post(
                f"/v1beta/models/{self.model}:batchEmbedContents",
                headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
                json={
                    "requests": [
                        {
                            "model": f"models/{self.model}",
                            "content": {"parts": [{"text": text}]},
                            "taskType": "CLUSTERING",
                            "outputDimensionality": self._dim,
                        }
                        for text in batch
                    ]
                },
            )

        # The free embedding tier's real 429s are transient dips (measured: two batches
        # in a row can fail then the next two immediately succeed with no change in
        # request pattern), not a hard wall - with_retries' default ~15s backoff window
        # (base_delay=0.5, 5 tries) isn't patient enough to ride them out. A longer base
        # delay with more tries (2+4+8+16+32+64 ≈ 126s worst case) reliably does.
        response = await with_retries(_request, max_tries=6, base_delay=2.0)
        response.raise_for_status()
        payload = response.json()
        return [
            _l2_normalise(np.array(embedding["values"], dtype=np.float32))
            for embedding in payload["embeddings"]
        ]


class FakeEmbedder:
    """Deterministic embedder for tests: a hash-seeded vector per text, no network."""

    def __init__(self, dim: int = 8, model: str = "fake-embedder") -> None:
        self.model = model
        self.call_count = 0
        self._dim = dim

    async def embed_raw(self, texts: list[str]) -> list[np.ndarray]:
        self.call_count += 1
        vectors = []
        for text in texts:
            seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**32)
            rng = np.random.default_rng(seed)
            vectors.append(_l2_normalise(rng.standard_normal(self._dim).astype(np.float32)))
        return vectors


async def embed_texts(
    session: Session,
    embedder: Embedder,
    texts: dict[str, str],
) -> dict[str, np.ndarray]:
    """Embed {text_hash: text}, reading/writing `EmbeddingCache` so a hash already cached
    for this embedder's model is never re-embedded (§4.3)."""
    result: dict[str, np.ndarray] = {}
    to_embed: dict[str, str] = {}

    for text_hash, text in texts.items():
        cached = session.get(EmbeddingCache, (text_hash, embedder.model))
        if cached is not None:
            result[text_hash] = _bytes_to_vector(cached.vector)
        else:
            to_embed[text_hash] = text

    if to_embed:
        hashes = list(to_embed.keys())
        vectors = await embedder.embed_raw([to_embed[h] for h in hashes])
        for text_hash, vector in zip(hashes, vectors, strict=True):
            result[text_hash] = vector
            session.add(
                EmbeddingCache(
                    text_hash=text_hash,
                    model=embedder.model,
                    dim=len(vector),
                    vector=_vector_to_bytes(vector),
                )
            )
        session.commit()

    return result
