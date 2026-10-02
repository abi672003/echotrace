import json
import re
from collections.abc import Awaitable, Callable
from typing import Protocol

import httpx

from app.config import get_settings
from app.services.ratelimit import get_bucket, with_retries

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com"
# httpx defaults to a 5s timeout, which a real LLM completion (especially a reasoning
# model, or a long agent-context prompt) can easily exceed - measured a real
# httpx.ReadTimeout against Gemini during Task 3.14's agent step.
LLM_HTTP_TIMEOUT = 60.0

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)

_REPAIR_PROMPT = (
    "That was not valid JSON. Reply again with exactly one valid JSON object, "
    "no prose, no code fences."
)


class LLMJSONError(Exception):
    """Raised when a model's response isn't valid JSON even after one repair retry."""


def strip_code_fences(text: str) -> str:
    return _CODE_FENCE_RE.sub("", text).strip()


class LLM(Protocol):
    model: str
    call_count: int

    async def complete_json(
        self, system: str, messages: list[dict[str, str]], schema: dict
    ) -> dict:
        """Return one parsed JSON object matching `schema`'s intent."""
        ...


async def _complete_json_with_repair(
    call: Callable[[str, list[dict[str, str]]], Awaitable[str]],
    system: str,
    messages: list[dict[str, str]],
) -> dict:
    raw = await call(system, messages)
    try:
        return json.loads(strip_code_fences(raw))
    except json.JSONDecodeError:
        repair_messages = [
            *messages,
            {"role": "assistant", "content": raw},
            {"role": "user", "content": _REPAIR_PROMPT},
        ]
        raw_retry = await call(system, repair_messages)
        try:
            return json.loads(strip_code_fences(raw_retry))
        except json.JSONDecodeError as exc:
            raise LLMJSONError(f"Model returned invalid JSON twice: {raw_retry!r}") from exc


class GroqLLM:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        settings = get_settings()
        self.model = settings.GROQ_CHAT_MODEL
        self.call_count = 0
        self._api_key = settings.GROQ_API_KEY.get_secret_value()
        self._client = client or httpx.AsyncClient(base_url=GROQ_BASE_URL, timeout=LLM_HTTP_TIMEOUT)
        self._bucket = get_bucket("groq")

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _call(self, system: str, messages: list[dict[str, str]]) -> str:
        await self._bucket.acquire()
        self.call_count += 1

        async def _request() -> httpx.Response:
            return await self._client.post(
                "/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "system", "content": system}, *messages],
                    "response_format": {"type": "json_object"},
                },
            )

        response = await with_retries(_request)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    async def complete_json(
        self, system: str, messages: list[dict[str, str]], schema: dict
    ) -> dict:
        return await _complete_json_with_repair(self._call, system, messages)


class GeminiLLM:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        settings = get_settings()
        self.model = settings.GEMINI_CHAT_MODEL
        self.call_count = 0
        self._api_key = settings.GEMINI_API_KEY.get_secret_value()
        self._client = client or httpx.AsyncClient(base_url=GEMINI_BASE_URL, timeout=LLM_HTTP_TIMEOUT)
        self._bucket = get_bucket("gemini")

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _call(self, system: str, messages: list[dict[str, str]]) -> str:
        await self._bucket.acquire()
        self.call_count += 1

        contents = [
            {
                "role": "model" if message["role"] == "assistant" else "user",
                "parts": [{"text": message["content"]}],
            }
            for message in messages
        ]
        if not contents:
            # Gemini rejects an empty `contents` array outright ("contents is not
            # specified"), unlike Groq/OpenAI-style APIs which accept a system-only
            # exchange. The agent's first turn has no prior messages (all context lives
            # in the system prompt), so give Gemini a minimal turn to respond to.
            contents = [{"role": "user", "parts": [{"text": "Begin."}]}]

        async def _request() -> httpx.Response:
            return await self._client.post(
                f"/v1beta/models/{self.model}:generateContent",
                headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
                json={
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": contents,
                    "generationConfig": {"responseMimeType": "application/json"},
                },
            )

        response = await with_retries(_request)
        response.raise_for_status()
        payload = response.json()
        return payload["candidates"][0]["content"]["parts"][0]["text"]

    async def complete_json(
        self, system: str, messages: list[dict[str, str]], schema: dict
    ) -> dict:
        return await _complete_json_with_repair(self._call, system, messages)


class FallbackLLM:
    """Tries `primary`; on any failure, switches to `secondary` for that call (§9)."""

    def __init__(self, primary: LLM, secondary: LLM) -> None:
        self.primary = primary
        self.secondary = secondary
        self.used_fallback = False
        self.model = primary.model

    @property
    def call_count(self) -> int:
        return self.primary.call_count + self.secondary.call_count

    async def complete_json(
        self, system: str, messages: list[dict[str, str]], schema: dict
    ) -> dict:
        try:
            return await self.primary.complete_json(system, messages, schema)
        except Exception:
            self.used_fallback = True
            return await self.secondary.complete_json(system, messages, schema)


class FakeLLM:
    """Scripted LLM for tests: each scripted string is consumed in order, with the same
    strip-fences + one-repair-retry contract as the real implementations, no network."""

    def __init__(self, scripted_responses: list[str]) -> None:
        self.model = "fake-llm"
        self.call_count = 0
        self._responses = list(scripted_responses)

    async def _call(self, system: str, messages: list[dict[str, str]]) -> str:
        self.call_count += 1
        if not self._responses:
            raise LLMJSONError("FakeLLM has no more scripted responses.")
        return self._responses.pop(0)

    async def complete_json(
        self, system: str, messages: list[dict[str, str]], schema: dict
    ) -> dict:
        return await _complete_json_with_repair(self._call, system, messages)
