"""Async client for the GDELT DOC 2.0 API — free, no API key, indexes global
online news within roughly 15 minutes of publication.

Docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/

Note: this dev sandbox's network is allowlisted to package registries only,
so this client's live behavior against api.gdeltproject.org has not been
exercised end-to-end from here — only unit-tested against a mocked
transport (see tests/test_gdelt.py). Verify connectivity on first real
deployment.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
DEFAULT_TIMEOUT_SECONDS = 15.0
MAX_QUERY_LEN = 250  # GDELT rejects overly long queries

# Frontend-facing timespan choices mapped to GDELT's accepted syntax.
TIMESPAN_CHOICES = {
    "24h": "1d",
    "7d": "1w",
    "30d": "1m",
}


class GdeltError(Exception):
    pass


async def search(
    query: str,
    timespan: str = "1w",
    maxrecords: int = 30,
    client: httpx.AsyncClient | None = None,
) -> list[dict]:
    """Query GDELT DOC 2.0 for candidate near-duplicate articles.

    Returns a list of {url, title, seendate, domain} dicts (empty list on
    any failure — retrieval degrades gracefully rather than raising, since
    a live web search having zero/failed results is a normal outcome, not
    a bug).
    """
    if not query.strip():
        return []

    params = {
        "query": query[:MAX_QUERY_LEN],
        "mode": "artlist",
        "format": "json",
        "maxrecords": min(max(maxrecords, 1), 250),
        "timespan": timespan,
        "sort": "hybridrel",
    }

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS)
    try:
        resp = await client.get(BASE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        logger.warning("GDELT search failed for query %r: %s", query, e)
        return []
    except ValueError as e:
        # GDELT returns HTML (not JSON) on some malformed-query cases
        logger.warning("GDELT returned non-JSON for query %r: %s", query, e)
        return []
    finally:
        if owns_client:
            await client.aclose()

    articles = data.get("articles", []) if isinstance(data, dict) else []
    results = []
    for a in articles:
        url = a.get("url")
        if not url:
            continue
        results.append(
            {
                "url": url,
                "title": a.get("title", ""),
                "seendate": a.get("seendate", ""),
                "domain": a.get("domain", ""),
            }
        )
    return results
