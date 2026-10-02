import json
from pathlib import Path

from app.agent.prompts import (
    DOCKET_SUMMARY_SYSTEM_PROMPT,
    SYSTEM_PROMPT_TEMPLATE,
    ToolSpec,
    render_docket_summary_user_message,
    render_system_prompt,
    render_tool_specs,
)

ARCHITECTURE_PATH = Path(__file__).resolve().parents[2] / "docs" / "ARCHITECTURE.md"


def test_system_prompt_matches_architecture_doc_verbatim() -> None:
    lines = ARCHITECTURE_PATH.read_text(encoding="utf-8").splitlines()
    spec_block = "\n".join(lines[327:345]) + "\n"  # lines 328-345, 0-indexed
    assert SYSTEM_PROMPT_TEMPLATE == spec_block


def test_render_system_prompt_substitutes_placeholders_without_touching_json_braces() -> None:
    rendered = render_system_prompt("- noop(): does nothing", '{"size": 3}')
    assert "Available tools: - noop(): does nothing" in rendered
    assert 'Family context: {"size": 3}' in rendered
    # the literal {"thought","action","args"} in the rules must survive untouched
    assert '{"thought","action","args"}' in rendered


def test_render_tool_specs_formats_each_tool() -> None:
    tools = [
        ToolSpec(name="timeline", description="member counts per hour", args={}),
        ToolSpec(name="compare", description="compare two docs", args={"doc_a": "int", "doc_b": "int"}),
    ]
    rendered = render_tool_specs(tools)
    assert "- timeline(): member counts per hour" in rendered
    assert "- compare(doc_a: int, doc_b: int): compare two docs" in rendered


def test_docket_summary_system_prompt_instructs_against_banned_vocabulary() -> None:
    # The prompt must forbid these words in the model's OUTPUT; mentioning them here, as
    # part of the instruction not to use them, is correct and expected.
    assert "150 words" in DOCKET_SUMMARY_SYSTEM_PROMPT
    assert "never call submitters fake, bots, or fraudulent" in DOCKET_SUMMARY_SYSTEM_PROMPT.lower()


def test_render_docket_summary_user_message_embeds_verdicts_as_json() -> None:
    verdicts = [{"type": "form_letter", "confidence": "high", "size": 48}]
    message = render_docket_summary_user_message(verdicts)
    assert json.dumps(verdicts) in message
