"""Near-duplicate retrieval over the ChromaDB corpus built by scripts/build_chroma.py."""

from pathlib import Path

import chromadb

from echotrace.retrieval.embed import embed_texts

CHROMA_DIR = Path(__file__).resolve().parents[3] / "db" / "chroma"
COLLECTION_NAME = "news_copy_articles"

_client = None


def get_collection():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client.get_collection(COLLECTION_NAME)


def find_near_duplicates(text: str, k: int = 10, exclude_id: str | None = None) -> list[dict]:
    """Return up to k near-duplicate candidates for `text`, each as
    {id, text, similarity} sorted by similarity descending. `similarity`
    is 1 - cosine_distance (ChromaDB's hnsw:space is cosine)."""
    collection = get_collection()
    query_embedding = embed_texts([text])[0].tolist()

    n_results = k + 1 if exclude_id else k
    result = collection.query(query_embeddings=[query_embedding], n_results=n_results)

    candidates = []
    for doc_id, doc_text, distance in zip(
        result["ids"][0], result["documents"][0], result["distances"][0]
    ):
        if doc_id == exclude_id:
            continue
        candidates.append({"id": doc_id, "text": doc_text, "similarity": 1.0 - distance})

    return candidates[:k]
