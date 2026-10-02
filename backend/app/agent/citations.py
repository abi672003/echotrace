from dataclasses import dataclass
from typing import Any

CONFIDENCE_LEVELS = ["low", "medium", "high"]


def lower_confidence(confidence: str) -> str:
    if confidence not in CONFIDENCE_LEVELS:
        return confidence
    index = CONFIDENCE_LEVELS.index(confidence)
    return CONFIDENCE_LEVELS[max(0, index - 1)]


def extract_ids_from_observation(observation: Any) -> set[int]:
    """Recursively collect every document id a tool's observation revealed to the
    agent: any `id`, `doc_a`, or `doc_b` integer value at any nesting level."""
    ids: set[int] = set()

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("id", "doc_a", "doc_b") and isinstance(value, int):
                    ids.add(value)
                else:
                    _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(observation)
    return ids


@dataclass(frozen=True)
class CitationValidationResult:
    cited_document_ids: list[int]
    confidence: str
    citations_corrected: bool


def validate_citations(
    cited_ids: list[int],
    family_member_ids: set[int],
    seen_tool_ids: set[int],
    confidence: str,
) -> CitationValidationResult:
    """§7: allowed ids = family members ∪ ids returned by any tool this trace. Invalid
    ids are dropped; if fewer than 2 remain, confidence drops one level and
    `citations_corrected=True`."""
    allowed = family_member_ids | seen_tool_ids
    valid = [cid for cid in cited_ids if cid in allowed]
    corrected = len(valid) != len(cited_ids)

    if len(valid) < 2:
        confidence = lower_confidence(confidence)
        corrected = True

    return CitationValidationResult(
        cited_document_ids=valid, confidence=confidence, citations_corrected=corrected
    )
