"""Agentic decision loop: Claude Haiku decides whether evidence is
sufficient, whether to search again, and whether to escalate to a human,
then outputs a verdict with a cited evidence trail.

Retrieval, detection, and aggregation (all real, deterministic pipeline
steps) supply evidence; the agent's job is to reason over that evidence,
not to re-derive it — it can only pull more evidence via the
search_more_duplicates tool, never fabricate any.

Evidence is gathered from the live web (retrieval/live_search.py) — the
same production retrieval path /api/investigate uses — so the agent's
verdict reflects real, current near-duplicate evidence, not the static
demo corpus.
"""

import asyncio
import json
import os
from pathlib import Path

from anthropic import AsyncAnthropic
from dotenv import load_dotenv

from echotrace.aggregation.aggregate import aggregate
from echotrace.detection.detector import score_text
from echotrace.retrieval.live_search import find_live_near_duplicates

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

MODEL = "claude-haiku-4-5-20251001"
MAX_TURNS = 4
INITIAL_K = 5
EXPANDED_K = 15

SYSTEM_PROMPT = """You are EchoTrace's verdict agent. You decide whether a news article is \
independent reporting or an AI-reworded content-farm copy, using retrieval \
and detection evidence gathered from the live web's near-duplicate \
articles.

You will be shown: the target article's own single-instance AI-text-detector \
score, its retrieved near-duplicate copies (each with a similarity score and \
its own detector score), and an aggregated score computed by weighting each \
duplicate's evidence by its similarity to the target.

Decide:
1. Is this evidence sufficient to reach a verdict, or should you search for \
more duplicates first (call search_more_duplicates — use this if fewer than \
2 duplicates were found, or if the evidence is contradictory)?
2. If the evidence remains ambiguous or too thin even after searching \
again, escalate to a human reviewer instead of guessing.
3. Otherwise submit a final verdict citing the specific evidence (which \
duplicate ids, their similarities and scores) that justifies it.

Never invent a duplicate, similarity, or score that wasn't returned by a tool."""

TOOLS = [
    {
        "name": "search_more_duplicates",
        "description": "Expand the near-duplicate search to a larger candidate pool when the initial evidence is too thin or contradictory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why more evidence is needed."}
            },
            "required": ["reason"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": "Escalate to human review when evidence remains ambiguous after searching.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
            },
            "required": ["reason"],
        },
    },
    {
        "name": "submit_verdict",
        "description": "Submit the final verdict with cited evidence.",
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["independent_reporting", "ai_reworded_copy"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reasoning": {"type": "string", "description": "Must cite specific duplicate ids/scores/similarities."},
            },
            "required": ["verdict", "confidence", "reasoning"],
        },
    },
]


async def _gather_evidence(article_text: str, target_url: str | None, k: int) -> dict:
    single_score = await asyncio.to_thread(score_text, article_text)
    duplicates_raw = await find_live_near_duplicates(article_text, k=k, exclude_url=target_url)

    async def _score(dup: dict) -> dict:
        s = await asyncio.to_thread(score_text, dup["text"])
        return {"id": dup["id"], "similarity": dup["similarity"], "score": s}

    duplicates = await asyncio.gather(*(_score(d) for d in duplicates_raw))
    result = aggregate(single_score, list(duplicates))
    return result.to_dict()


async def run_agent(article_text: str, target_url: str | None = None) -> dict:
    client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    evidence = await _gather_evidence(article_text, target_url, k=INITIAL_K)
    search_log = [{"k": INITIAL_K, "n_duplicates_found": len(evidence["evidence"])}]

    messages = [
        {
            "role": "user",
            "content": f"Target article (first 500 chars): {article_text[:500]!r}\n\n"
            f"Evidence:\n{json.dumps(evidence, indent=2)}",
        }
    ]

    for turn in range(MAX_TURNS):
        response = await client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        tool_use = next((b for b in response.content if b.type == "tool_use"), None)
        if tool_use is None:
            # Model didn't call a tool — treat as escalation, don't guess a verdict.
            return {
                "verdict": "escalated",
                "reason": "agent did not submit a structured decision",
                "evidence": evidence,
                "search_log": search_log,
            }

        if tool_use.name == "submit_verdict":
            return {**tool_use.input, "evidence": evidence, "search_log": search_log}

        if tool_use.name == "escalate_to_human":
            return {"verdict": "escalated", **tool_use.input, "evidence": evidence, "search_log": search_log}

        if tool_use.name == "search_more_duplicates":
            evidence = await _gather_evidence(article_text, target_url, k=EXPANDED_K)
            search_log.append({"k": EXPANDED_K, "n_duplicates_found": len(evidence["evidence"])})
            messages.append({"role": "assistant", "content": response.content})
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": json.dumps(evidence, indent=2),
                        }
                    ],
                }
            )
            continue

    return {
        "verdict": "escalated",
        "reason": f"no decision reached within {MAX_TURNS} turns",
        "evidence": evidence,
        "search_log": search_log,
    }
