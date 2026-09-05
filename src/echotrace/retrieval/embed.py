"""Near-duplicate retrieval: embed articles with all-MiniLM-L6-v2.

Per constraint 0.3, the model is loaded from a local folder path only —
never a Hugging Face hub string — so this never attempts a network call.
"""

from pathlib import Path

from sentence_transformers import SentenceTransformer

MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "all-MiniLM-L6-v2"

_model = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Local model folder not found at {MODEL_PATH}. "
                "This project loads models from local paths only (never the HF hub) — "
                "see constraint 0.3 in the project brief."
            )
        _model = SentenceTransformer(str(MODEL_PATH))
    return _model


def embed_texts(texts: list[str]):
    return get_model().encode(texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True)
