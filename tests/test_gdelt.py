"""GDELT client tests — network mocked via httpx.MockTransport, since this
dev sandbox can't reach the real api.gdeltproject.org (see retrieval/gdelt.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import httpx
import pytest

from echotrace.retrieval.gdelt import search


@pytest.mark.asyncio
async def test_search_parses_articles():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "query" in request.url.params
        return httpx.Response(
            200,
            json={
                "articles": [
                    {"url": "https://example.com/a", "title": "Story A", "seendate": "20260101", "domain": "example.com"},
                    {"url": "https://example.com/b", "title": "Story B", "seendate": "20260102", "domain": "example.com"},
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    results = await search("city council budget", client=client)
    await client.aclose()

    assert len(results) == 2
    assert results[0]["url"] == "https://example.com/a"
    assert results[0]["title"] == "Story A"


@pytest.mark.asyncio
async def test_search_skips_articles_without_url():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"articles": [{"title": "No URL here"}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    results = await search("anything", client=client)
    await client.aclose()

    assert results == []


@pytest.mark.asyncio
async def test_search_returns_empty_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    results = await search("anything", client=client)
    await client.aclose()

    assert results == []


@pytest.mark.asyncio
async def test_search_returns_empty_on_non_json_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    results = await search("anything", client=client)
    await client.aclose()

    assert results == []


@pytest.mark.asyncio
async def test_search_empty_query_short_circuits():
    results = await search("   ")
    assert results == []
