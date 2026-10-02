import json

import pytest
import respx
from httpx import Response

from app.services.llm import (
    GEMINI_BASE_URL,
    GROQ_BASE_URL,
    FakeLLM,
    FallbackLLM,
    GeminiLLM,
    GroqLLM,
    LLMJSONError,
    strip_code_fences,
)


def test_strip_code_fences_removes_json_fence() -> None:
    assert strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_code_fences_removes_plain_fence() -> None:
    assert strip_code_fences('```\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_code_fences_is_noop_on_plain_json() -> None:
    assert strip_code_fences('{"a": 1}') == '{"a": 1}'


@pytest.mark.asyncio
async def test_fake_llm_returns_scripted_json() -> None:
    llm = FakeLLM(['{"thought": "ok", "action": "noop", "args": {}}'])
    result = await llm.complete_json("sys", [{"role": "user", "content": "hi"}], {})
    assert result == {"thought": "ok", "action": "noop", "args": {}}
    assert llm.call_count == 1


@pytest.mark.asyncio
async def test_fake_llm_strips_code_fences() -> None:
    llm = FakeLLM(['```json\n{"a": 1}\n```'])
    result = await llm.complete_json("sys", [], {})
    assert result == {"a": 1}


@pytest.mark.asyncio
async def test_fake_llm_repairs_once_after_invalid_json() -> None:
    llm = FakeLLM(["not valid json at all", '{"a": 2}'])
    result = await llm.complete_json("sys", [{"role": "user", "content": "hi"}], {})
    assert result == {"a": 2}
    assert llm.call_count == 2  # one bad call, one repair call


@pytest.mark.asyncio
async def test_fake_llm_raises_after_two_invalid_responses() -> None:
    llm = FakeLLM(["garbage one", "garbage two"])
    with pytest.raises(LLMJSONError):
        await llm.complete_json("sys", [], {})
    assert llm.call_count == 2


@pytest.mark.asyncio
async def test_fallback_llm_uses_primary_when_it_succeeds() -> None:
    primary = FakeLLM(['{"from": "primary"}'])
    secondary = FakeLLM(['{"from": "secondary"}'])
    llm = FallbackLLM(primary, secondary)

    result = await llm.complete_json("sys", [], {})

    assert result == {"from": "primary"}
    assert llm.used_fallback is False
    assert llm.call_count == 1


@pytest.mark.asyncio
async def test_fallback_llm_switches_to_secondary_on_primary_failure() -> None:
    primary = FakeLLM(["garbage", "garbage"])  # exhausts repair -> raises
    secondary = FakeLLM(['{"from": "secondary"}'])
    llm = FallbackLLM(primary, secondary)

    result = await llm.complete_json("sys", [], {})

    assert result == {"from": "secondary"}
    assert llm.used_fallback is True


@pytest.mark.asyncio
@respx.mock
async def test_groq_llm_complete_json_parses_real_shaped_response() -> None:
    respx.post(f"{GROQ_BASE_URL}/chat/completions").mock(
        return_value=Response(
            200,
            json={"choices": [{"message": {"content": '{"verdict": "ok"}'}}]},
        )
    )
    llm = GroqLLM()
    result = await llm.complete_json("sys", [{"role": "user", "content": "hi"}], {})
    assert result == {"verdict": "ok"}
    assert llm.call_count == 1
    await llm.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_gemini_llm_complete_json_parses_real_shaped_response() -> None:
    respx.post(f"{GEMINI_BASE_URL}/v1beta/models/gemini-3.8-flash:generateContent").mock(
        return_value=Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": '{"verdict": "ok"}'}]}}
                ]
            },
        )
    )
    llm = GeminiLLM()
    result = await llm.complete_json("sys", [{"role": "user", "content": "hi"}], {})
    assert result == {"verdict": "ok"}
    assert llm.call_count == 1
    await llm.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_gemini_llm_never_sends_empty_contents_on_first_turn() -> None:
    """Gemini rejects an empty `contents` array ('contents is not specified', 400) -
    discovered running the real agent loop (Task 3.14), whose first turn has no prior
    messages since all context lives in the system prompt. Groq/OpenAI-style APIs
    tolerate a system-only exchange; Gemini does not, so this needs its own guard."""
    route = respx.post(f"{GEMINI_BASE_URL}/v1beta/models/gemini-3.8-flash:generateContent").mock(
        return_value=Response(
            200, json={"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]}
        )
    )
    llm = GeminiLLM()
    result = await llm.complete_json("sys", [], {})  # empty messages: the agent's first turn
    assert result == {"ok": True}
    sent_body = route.calls.last.request.content
    assert json.loads(sent_body)["contents"] != []
    await llm.aclose()
