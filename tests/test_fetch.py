"""fetch.py tests — network mocked via httpx.MockTransport; trafilatura
extraction itself runs for real (it's a local, offline HTML parser, so this
genuinely exercises the extraction path without needing live connectivity)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import httpx
import pytest

from echotrace.retrieval.fetch import fetch_and_extract, fetch_many, is_allowed

ARTICLE_HTML = """
<html><head><title>Council Approves New Budget</title></head>
<body><article>
<h1>Council Approves New Budget</h1>
<p>The city council voted on Tuesday to approve a new budget after a lengthy
debate that lasted well into the evening. Several members raised concerns
about funding allocations for public transportation and housing services,
while the mayor defended the plan as fiscally responsible and necessary for
the city's continued growth over the coming decade.</p>
<p>Residents who attended the meeting expressed a mix of support and
skepticism, with some praising the increased investment in infrastructure
and others worried about the tax implications for homeowners across the
district in the years ahead.</p>
</article></body></html>
"""


def _make_client(allow_robots: bool = True, html: str = ARTICLE_HTML, status: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            body = "User-agent: *\nDisallow: /\n" if not allow_robots else "User-agent: *\nAllow: /\n"
            return httpx.Response(200, text=body)
        return httpx.Response(status, text=html)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_fetch_and_extract_real_article():
    client = _make_client()
    result = await fetch_and_extract("https://example.com/story", client)
    await client.aclose()

    assert result is not None
    assert "council" in result["text"].lower()
    assert result["domain"] == "example.com"
    assert len(result["text"]) >= 200


@pytest.mark.asyncio
async def test_robots_disallow_blocks_fetch():
    # distinct domain from other tests: the per-domain robots.txt cache is
    # a module-level global, so reusing example.com here would read back
    # another test's cached "Allow" result instead of hitting this mock.
    client = _make_client(allow_robots=False)
    allowed = await is_allowed("https://blocked.example.com/story", client)
    result = await fetch_and_extract("https://blocked.example.com/story", client)
    await client.aclose()

    assert allowed is False
    assert result is None


@pytest.mark.asyncio
async def test_short_page_is_rejected():
    client = _make_client(html="<html><body><p>Too short.</p></body></html>")
    result = await fetch_and_extract("https://example.com/stub", client)
    await client.aclose()

    assert result is None


@pytest.mark.asyncio
async def test_http_error_returns_none():
    client = _make_client(status=404)
    result = await fetch_and_extract("https://example.com/missing", client)
    await client.aclose()

    assert result is None


@pytest.mark.asyncio
async def test_fetch_many_skips_failures_and_returns_successes(monkeypatch):
    async def fake_fetch_and_extract(url, client):
        if "bad" in url:
            return None
        return {"url": url, "title": "T", "text": "x" * 300, "domain": "example.com"}

    monkeypatch.setattr("echotrace.retrieval.fetch.fetch_and_extract", fake_fetch_and_extract)

    results = await fetch_many(["https://example.com/good1", "https://example.com/bad", "https://example.com/good2"])
    urls = {r["url"] for r in results}
    assert urls == {"https://example.com/good1", "https://example.com/good2"}


@pytest.mark.asyncio
async def test_fetch_many_empty_input():
    assert await fetch_many([]) == []
