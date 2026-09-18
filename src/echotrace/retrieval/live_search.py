"""Live near-duplicate retrieval: GDELT search + fetch/extract + local
embedding rank — the production replacement for the static ChromaDB corpus
in retrieval/search.py.

Orchestration: build a search query from the target text (keywords.py) →
GDELT search (gdelt.py) → concurrent fetch+extract of each candidate URL,
cached in the `fetched_articles` table so a re-investigated story doesn't
get re-scraped (fetch.py) → rank by embedding cosine similarity using the
same local MiniLM model the rest of the app already uses (embed.py).

Returns the same `{id, text, similarity}` shape the static retrieval always
did, so `aggregation/aggregate.py` and `agent/decision.py` need no changes.
`id` is the source URL — an opaque string key, same contract as before.
"""

from sqlalchemy import select
from sqlalchemy.engine import Connection

from echotrace.db import fetched_articles, get_connection, upsert_ignore
from echotrace.retrieval.embed import embed_texts
from echotrace.retrieval.fetch import fetch_many
from echotrace.retrieval.gdelt import search as gdelt_search
from echotrace.retrieval.keywords import build_gdelt_query

DEFAULT_TIMESPAN = "1w"
# Search wider than k: robots.txt blocks, paywalls, and unparseable pages
# mean a meaningful fraction of GDELT candidates never make it to scoring.
GDELT_MAXRECORDS = 40


def _cached_lookup(conn: Connection, urls: list[str]) -> dict[str, dict]:
    if not urls:
        return {}
    rows = conn.execute(select(fetched_articles).where(fetched_articles.c.url.in_(urls))).fetchall()
    return {r.url: {"url": r.url, "title": r.title, "text": r.text, "domain": r.domain} for r in rows}


def _cache_write(conn: Connection, fetched: list[dict]) -> None:
    rows = [{"url": f["url"], "title": f["title"], "text": f["text"], "domain": f["domain"]} for f in fetched]
    upsert_ignore(conn, fetched_articles, rows)
    conn.commit()


async def find_live_near_duplicates(
    target_text: str,
    k: int = 5,
    timespan: str = DEFAULT_TIMESPAN,
    exclude_url: str | None = None,
) -> list[dict]:
    """Search the live web for near-duplicates of `target_text`.

    Returns up to k {id, text, similarity, title, domain} dicts sorted by
    embedding-cosine similarity to the target, descending. May return fewer
    than k (or zero) — a thin or empty result is a normal outcome of
    searching the live web, not an error; the agent layer already treats
    "fewer than 2 duplicates" as a reason to search again or escalate.
    """
    query = build_gdelt_query(target_text)
    candidates = await gdelt_search(query, timespan=timespan, maxrecords=GDELT_MAXRECORDS)
    urls = [c["url"] for c in candidates if c["url"] != exclude_url]

    conn = get_connection()
    try:
        cached = _cached_lookup(conn, urls)
        to_fetch = [u for u in urls if u not in cached]
        freshly_fetched = await fetch_many(to_fetch) if to_fetch else []
        if freshly_fetched:
            _cache_write(conn, freshly_fetched)
    finally:
        conn.close()

    fetched_by_url = {**cached, **{f["url"]: f for f in freshly_fetched}}
    resolved = [fetched_by_url[u] for u in urls if u in fetched_by_url]
    if not resolved:
        return []

    texts = [target_text] + [a["text"] for a in resolved]
    embeddings = embed_texts(texts)
    target_vec, candidate_vecs = embeddings[0], embeddings[1:]

    # embed_texts L2-normalizes (retrieval/embed.py), so cosine similarity
    # is just the dot product.
    similarities = candidate_vecs @ target_vec

    ranked = sorted(zip(resolved, similarities), key=lambda pair: float(pair[1]), reverse=True)

    return [
        {
            "id": a["url"],
            "text": a["text"],
            "similarity": float(sim),
            "title": a["title"],
            "domain": a["domain"],
        }
        for a, sim in ranked[:k]
    ]
