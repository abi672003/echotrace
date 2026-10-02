import difflib
import re

import numpy as np
from sqlmodel import Session

from app.models import EmbeddingCache
from app.services.features import jaccard, word_shingles

_WORD_SPAN_RE = re.compile(r"[a-zA-Z0-9']+")
MIN_SHARED_WORDS = 5


def _tokenize_with_spans(text: str) -> list[tuple[str, int, int]]:
    return [(m.group().lower(), m.start(), m.end()) for m in _WORD_SPAN_RE.finditer(text)]


def shared_spans(text_a: str, text_b: str, min_words: int = MIN_SHARED_WORDS) -> list[dict]:
    """Shared word runs of at least `min_words`, merged into contiguous character ranges
    in each text (via `difflib`'s matching blocks over word tokens, not characters)."""
    tokens_a = _tokenize_with_spans(text_a)
    tokens_b = _tokenize_with_spans(text_b)
    words_a = [token[0] for token in tokens_a]
    words_b = [token[0] for token in tokens_b]

    matcher = difflib.SequenceMatcher(None, words_a, words_b, autojunk=False)
    spans: list[dict] = []
    for block in matcher.get_matching_blocks():
        if block.size < min_words:
            continue
        a_start = tokens_a[block.a][1]
        a_end = tokens_a[block.a + block.size - 1][2]
        b_start = tokens_b[block.b][1]
        b_end = tokens_b[block.b + block.size - 1][2]
        spans.append(
            {
                "a_start": a_start,
                "a_end": a_end,
                "b_start": b_start,
                "b_end": b_end,
                "text": text_a[a_start:a_end],
            }
        )
    return spans


def lexical_similarity(text_a: str, text_b: str) -> float:
    return jaccard(word_shingles(text_a), word_shingles(text_b))


def semantic_similarity(session: Session, model: str, hash_a: str, hash_b: str) -> float:
    """Cosine similarity between two documents' cached embeddings; 0.0 if either is
    not yet embedded (both vectors are already L2-normalised, so dot product = cosine)."""
    cache_a = session.get(EmbeddingCache, (hash_a, model))
    cache_b = session.get(EmbeddingCache, (hash_b, model))
    if cache_a is None or cache_b is None:
        return 0.0
    vector_a = np.frombuffer(cache_a.vector, dtype=np.float32)
    vector_b = np.frombuffer(cache_b.vector, dtype=np.float32)
    return float(np.dot(vector_a, vector_b))
