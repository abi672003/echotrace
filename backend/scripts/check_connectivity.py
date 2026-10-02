"""Connectivity check for EchoTrace's three external providers.

Run from backend/: python scripts\\check_connectivity.py
Reports OK / HTTP status / "blocked by network" per provider. Never prints key values.
"""
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.config import Settings, get_settings

TIMEOUT = 10.0


_NETWORK_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.ProxyError,
)


def _classify(request: Callable[[], httpx.Response]) -> str:
    try:
        response = request()
    except _NETWORK_ERRORS:
        return "blocked by network"
    if response.status_code < 300:
        return "OK"
    return f"HTTP {response.status_code}"


def check_regulations(settings: Settings) -> str:
    def request() -> httpx.Response:
        return httpx.get(
            "https://api.regulations.gov/v4/dockets",
            params={"page[size]": 5},
            headers={"X-Api-Key": settings.REGULATIONS_API_KEY.get_secret_value()},
            timeout=TIMEOUT,
        )

    return _classify(request)


def check_gemini(settings: Settings) -> str:
    def request() -> httpx.Response:
        return httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_EMBED_MODEL}:embedContent",
            headers={
                "x-goog-api-key": settings.GEMINI_API_KEY.get_secret_value(),
                "Content-Type": "application/json",
            },
            json={"content": {"parts": [{"text": "hello"}]}},
            timeout=TIMEOUT,
        )

    return _classify(request)


def check_groq(settings: Settings) -> str:
    headers = {"Content-Type": "application/json"}
    key = settings.GROQ_API_KEY.get_secret_value()
    if key:
        headers["Authorization"] = f"Bearer {key}"

    def request() -> httpx.Response:
        return httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json={
                "model": settings.GROQ_CHAT_MODEL,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
            },
            timeout=TIMEOUT,
        )

    return _classify(request)


def main() -> int:
    settings = get_settings()
    results = {
        "regulations.gov": check_regulations(settings),
        "gemini": check_gemini(settings),
        "groq": check_groq(settings),
    }

    blocked = False
    for provider, status in results.items():
        print(f"{provider}: {status}")
        if status == "blocked by network":
            blocked = True

    if blocked:
        print("\nOne or more hosts are blocked by the network. Stop and report before Phase 3.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
