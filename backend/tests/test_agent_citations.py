from app.agent.citations import (
    extract_ids_from_observation,
    lower_confidence,
    validate_citations,
)


def test_lower_confidence_steps_down_one_level() -> None:
    assert lower_confidence("high") == "medium"
    assert lower_confidence("medium") == "low"


def test_lower_confidence_floors_at_low() -> None:
    assert lower_confidence("low") == "low"


def test_extract_ids_from_list_members_style_observation() -> None:
    observation = [
        {"id": 1, "excerpt": "a"},
        {"id": 2, "excerpt": "b"},
    ]
    assert extract_ids_from_observation(observation) == {1, 2}


def test_extract_ids_from_compare_style_observation() -> None:
    observation = {"doc_a": 5, "doc_b": 7, "sem": 0.9, "lex": 0.2, "shared_phrases": []}
    assert extract_ids_from_observation(observation) == {5, 7}


def test_extract_ids_ignores_non_id_integers() -> None:
    observation = {"size": 12, "metrics": {"reword_index": 0.5}}
    assert extract_ids_from_observation(observation) == set()


def test_validate_citations_keeps_ids_seen_via_family_or_tools() -> None:
    result = validate_citations(
        cited_ids=[1, 2],
        family_member_ids={1, 2, 3},
        seen_tool_ids=set(),
        confidence="high",
    )
    assert result.cited_document_ids == [1, 2]
    assert result.confidence == "high"
    assert result.citations_corrected is False


def test_validate_citations_drops_hallucinated_id_and_keeps_valid_ones() -> None:
    result = validate_citations(
        cited_ids=[1, 999, 2],
        family_member_ids={1, 2, 3},
        seen_tool_ids=set(),
        confidence="high",
    )
    assert result.cited_document_ids == [1, 2]
    assert result.citations_corrected is True
    assert result.confidence == "high"  # still 2+ valid citations, no confidence drop


def test_validate_citations_lowers_confidence_when_fewer_than_two_remain() -> None:
    result = validate_citations(
        cited_ids=[999, 998, 1],
        family_member_ids={1, 2, 3},
        seen_tool_ids=set(),
        confidence="high",
    )
    assert result.cited_document_ids == [1]
    assert result.citations_corrected is True
    assert result.confidence == "medium"


def test_validate_citations_allows_ids_only_seen_via_tool_not_family() -> None:
    # search_similar can surface docs outside the family; citing them should be allowed.
    result = validate_citations(
        cited_ids=[1, 42],
        family_member_ids={1, 2, 3},
        seen_tool_ids={42},
        confidence="medium",
    )
    assert result.cited_document_ids == [1, 42]
    assert result.citations_corrected is False


def test_validate_citations_zero_valid_ids_lowers_confidence() -> None:
    result = validate_citations(
        cited_ids=[999, 998],
        family_member_ids={1, 2, 3},
        seen_tool_ids=set(),
        confidence="low",
    )
    assert result.cited_document_ids == []
    assert result.citations_corrected is True
    assert result.confidence == "low"  # already floored
