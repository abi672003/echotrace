import json
from dataclasses import dataclass

# Kept verbatim from ARCHITECTURE.md §7. Do not reword — the exact phrasing encodes the
# product-ethics rules (never conclude "campaign" from AI-style alone, never call
# submitters fake/bots/fraudulent, cite only seen IDs, one JSON object per turn).
SYSTEM_PROMPT_TEMPLATE = (
    "You review one family of public comments on a government regulation. The family was\n"
    "grouped automatically because its comments share meaning. Decide which type fits best:\n"
    "coordinated_paraphrase_campaign, form_letter, organic_agreement, insufficient_evidence.\n"
    "\n"
    "Rules:\n"
    '- Using AI to write is legitimate. Never conclude "campaign" from AI-style scores alone.\n'
    "  A campaign needs a family pattern: same argument, different wording, and supporting\n"
    "  signals such as a time burst or many distinct submitters in a short window.\n"
    "- Many people independently agreeing is organic_agreement, not a campaign. Varied\n"
    "  structure, personal details, and spread-out timing point that way.\n"
    "- Identical or near-identical text is form_letter. That is a normal, legitimate practice.\n"
    "- You cannot verify identities. Never call submitters fake, bots, or fraudulent.\n"
    "- Cite only comment IDs you have seen in tool observations. Cite 2 to 8.\n"
    "- Rationale: plain language, at most 120 words, name the metrics that decided it.\n"
    '- Reply with exactly one JSON object per turn: {"thought","action","args"}. No prose.\n'
    "\n"
    "Available tools: {tool_specs}\n"
    "Family context: {family_summary_json}\n"
)

DOCKET_SUMMARY_SYSTEM_PROMPT = (
    "You write a short summary of a docket's reviewed comment families for an agency "
    "analyst. Using AI to write is legitimate; you cannot verify identities; never call "
    "submitters fake, bots, or fraudulent. Plain language, at most 150 words. Reply with "
    'exactly one JSON object: {"summary": <text>}. No prose outside the JSON.'
)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args: dict[str, str]


def render_tool_specs(tools: list[ToolSpec]) -> str:
    lines = []
    for tool in tools:
        args_desc = ", ".join(f"{name}: {desc}" for name, desc in tool.args.items())
        lines.append(f"- {tool.name}({args_desc}): {tool.description}")
    return "\n".join(lines)


def render_system_prompt(tool_specs: str, family_summary_json: str) -> str:
    return SYSTEM_PROMPT_TEMPLATE.replace("{tool_specs}", tool_specs).replace(
        "{family_summary_json}", family_summary_json
    )


def render_docket_summary_user_message(verdicts: list[dict]) -> str:
    """`verdicts` must hold only type/confidence/size/rationale-level fields — never raw
    comment text (§7: "over the reviewed families' verdicts only, no raw text")."""
    return "Family verdicts:\n" + json.dumps(verdicts)
