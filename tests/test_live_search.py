"""live_search.py orchestration tests: GDELT + fetch are mocked (no live
network from this sandbox — see retrieval/gdelt.py); embedding + DB caching
run for real against a temp SQLite DB and the real local MiniLM model."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from echotrace.db import get_connection, reset_engine_for_tests
from echotrace.retrieval import live_search


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    reset_engine_for_tests(f"sqlite:///{(tmp_path / 'live_search_test.sqlite').as_posix()}")
    yield
    get_connection().close()


ARTICLE_A = (
    "The city council voted on Tuesday to approve a new municipal budget "
    "after a lengthy debate about public transportation funding and housing."
)
ARTICLE_B = (
    "City council members approved a new budget this week following an "
    "extended discussion over transit funding and affordable housing."
)
ARTICLE_UNRELATED = (
    "A local bakery announced it will open a second location downtown next "
    "spring, expanding its selection of pastries and specialty coffee."
)


@pytest.mark.asyncio
async def test_ranks_by_similarity_and_caches_fetches(monkeypatch):
    async def fake_gdelt_search(query, timespan="1w", maxrecords=40, client=None):
        return [
            {"url": "https://example.com/similar", "title": "Similar", "seendate": "", "domain": "example.com"},
            {"url": "https://example.com/unrelated", "title": "Unrelated", "seendate": "", "domain": "example.com"},
        ]

    fetch_calls = []

    async def fake_fetch_many(urls, concurrency=8, timeout=10.0):
        fetch_calls.append(list(urls))
        out = []
        for u in urls:
            if "similar" in u:
                out.append({"url": u, "title": "Similar", "text": ARTICLE_B, "domain": "example.com"})
            elif "unrelated" in u:
                out.append({"url": u, "title": "Unrelated", "text": ARTICLE_UNRELATED, "domain": "example.com"})
        return out

    monkeypatch.setattr(live_search, "gdelt_search", fake_gdelt_search)
    monkeypatch.setattr(live_search, "fetch_many", fake_fetch_many)

    results = await live_search.find_live_near_duplicates(ARTICLE_A, k=5)

    assert len(results) == 2
    # the semantically similar article should rank first
    assert results[0]["id"] == "https://example.com/similar"
    assert results[0]["similarity"] > results[1]["similarity"]
    assert fetch_calls == [["https://example.com/similar", "https://example.com/unrelated"]]

    # second call for the same URLs should hit the cache, not re-fetch
    fetch_calls.clear()
    results2 = await live_search.find_live_near_duplicates(ARTICLE_A, k=5)
    assert fetch_calls == []
    assert len(results2) == 2


@pytest.mark.asyncio
async def test_no_candidates_returns_empty_list(monkeypatch):
    async def fake_gdelt_search(query, timespan="1w", maxrecords=40, client=None):
        return []

    monkeypatch.setattr(live_search, "gdelt_search", fake_gdelt_search)

    results = await live_search.find_live_near_duplicates(ARTICLE_A, k=5)
    assert results == []


@pytest.mark.asyncio
async def test_excludes_target_url(monkeypatch):
    async def fake_gdelt_search(query, timespan="1w", maxrecords=40, client=None):
        return [
            {"url": "https://example.com/self", "title": "Self", "seendate": "", "domain": "example.com"},
            {"url": "https://example.com/other", "title": "Other", "seendate": "", "domain": "example.com"},
        ]

    async def fake_fetch_many(urls, concurrency=8, timeout=10.0):
        return [{"url": u, "title": "T", "text": ARTICLE_B, "domain": "example.com"} for u in urls]

    monkeypatch.setattr(live_search, "gdelt_search", fake_gdelt_search)
    monkeypatch.setattr(live_search, "fetch_many", fake_fetch_many)

    results = await live_search.find_live_near_duplicates(
        ARTICLE_A, k=5, exclude_url="https://example.com/self"
    )
    assert all(r["id"] != "https://example.com/self" for r in results)
    assert len(results) == 1
