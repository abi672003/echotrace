"""Fetch a candidate URL and extract its main article text, politely.

Every fetch is preceded by a robots.txt check (cached per-domain), runs
through a shared concurrency limit, and fails soft — a blocked, paywalled,
timed-out, or unparseable page is skipped, never a crash. This is what lets
`retrieval/live_search.py` treat "fewer duplicates than requested" as a
normal outcome of searching the live web, not an error.

Same caveat as gdelt.py: this dev sandbox can't reach arbitrary external
hosts, so live fetching against real publisher sites is unverified from
here — see tests/test_fetch.py for the mocked-transport coverage that does
run, and verify against a few real URLs on first deployment.
"""

import asyncio
import json
import logging
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura

logger = logging.getLogger(__name__)

USER_AGENT = (
    "EchoTraceBot/1.0 (+https://github.com/abi672003/echotrace; "
    "automated near-duplicate news verification, respects robots.txt)"
)
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_CONCURRENCY = 8
ROBOTS_CACHE_TTL_SECONDS = 3600
MIN_ARTICLE_CHARS = 200  # shorter than this, trafilatura likely grabbed a stub/error page

_robots_cache: dict[str, tuple[float, RobotFileParser]] = {}


async def _get_robots_parser(base_url: str, client: httpx.AsyncClient) -> RobotFileParser:
    now = time.time()
    cached = _robots_cache.get(base_url)
    if cached and now - cached[0] < ROBOTS_CACHE_TTL_SECONDS:
        return cached[1]

    rp = RobotFileParser()
    try:
        resp = await client.get(base_url.rstrip("/") + "/robots.txt", timeout=5.0)
        rp.parse(resp.text.splitlines() if resp.status_code == 200 else [])
    except httpx.HTTPError:
        rp.parse([])  # no robots.txt reachable -> treat as allow-all
    _robots_cache[base_url] = (now, rp)
    return rp


async def is_allowed(url: str, client: httpx.AsyncClient) -> bool:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    try:
        rp = await _get_robots_parser(base, client)
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True  # be permissive on robots-parsing failure


async def fetch_and_extract(url: str, client: httpx.AsyncClient) -> dict | None:
    """Fetch `url` and extract its main article text.

    Returns {url, title, text, domain} or None on any failure — blocked by
    robots.txt, network/timeout error, paywall, or a page trafilatura can't
    parse into a real article body.
    """
    if not await is_allowed(url, client):
        logger.info("robots.txt disallows fetching %s", url)
        return None

    try:
        resp = await client.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
        resp.raise_for_status()
        html = resp.text
    except httpx.HTTPError as e:
        logger.info("fetch failed for %s: %s", url, e)
        return None

    # CPU-bound HTML parsing — keep it off the event loop.
    raw = await asyncio.to_thread(
        trafilatura.extract,
        html,
        output_format="json",
        with_metadata=True,
        favor_precision=True,
    )
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None

    text = (parsed.get("text") or "").strip()
    if len(text) < MIN_ARTICLE_CHARS:
        return None

    return {
        "url": url,
        "title": parsed.get("title") or "",
        "text": text,
        "domain": urlparse(url).netloc,
    }


async def fetch_many(
    urls: list[str],
    concurrency: int = DEFAULT_CONCURRENCY,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[dict]:
    """Concurrently fetch+extract each URL. Returns only the ones that
    succeeded — a partial result set is the expected common case."""
    if not urls:
        return []

    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded(url: str, client: httpx.AsyncClient) -> dict | None:
        async with semaphore:
            return await fetch_and_extract(url, client)

    async with httpx.AsyncClient(timeout=timeout) as client:
        results = await asyncio.gather(
            *(_bounded(u, client) for u in urls), return_exceptions=True
        )

    out = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning("fetch task raised: %s", r)
            continue
        if r is not None:
            out.append(r)
    return out
