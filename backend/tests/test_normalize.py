from app.services.normalize import (
    clean_text,
    is_attachment_only,
    normalize_for_hash,
    submitter_hash,
    text_hash,
    word_count,
)


def test_clean_text_strips_html_tags() -> None:
    assert clean_text("<p>Hello <b>world</b></p>") == "Hello world"


def test_clean_text_unescapes_entities() -> None:
    assert clean_text("Tom &amp; Jerry &lt;3") == "Tom & Jerry <3"


def test_clean_text_collapses_whitespace() -> None:
    assert clean_text("Hello   \n\n  world\t!") == "Hello world !"


def test_normalize_for_hash_lowercases_and_strips_salutation() -> None:
    result = normalize_for_hash("Dear EPA,\n\nI OPPOSE this rule.")
    assert result == "i oppose this rule."


def test_normalize_for_hash_strips_to_whom_it_may_concern() -> None:
    result = normalize_for_hash("To Whom It May Concern: Please reconsider.")
    assert result == "please reconsider."


def test_text_hash_is_deterministic_and_sensitive_to_content() -> None:
    a = text_hash(normalize_for_hash("Dear EPA, I oppose this rule."))
    b = text_hash(normalize_for_hash("DEAR EPA,   I OPPOSE   this rule."))
    c = text_hash(normalize_for_hash("Dear EPA, I support this rule."))
    assert a == b  # same content modulo case/whitespace/salutation -> same hash
    assert a != c


def test_word_count_counts_whitespace_separated_tokens() -> None:
    assert word_count("one two three") == 3
    assert word_count("") == 0


def test_is_attachment_only_true_for_empty_text() -> None:
    assert is_attachment_only("", min_words=25) is True


def test_is_attachment_only_true_for_see_attached_phrase() -> None:
    assert is_attachment_only("See attached.", min_words=25) is True
    assert is_attachment_only("Please see the attachment", min_words=25) is True
    assert is_attachment_only("Comment attached.", min_words=25) is True


def test_is_attachment_only_true_for_short_text() -> None:
    short_text = " ".join(["word"] * 10)
    assert is_attachment_only(short_text, min_words=25) is True


def test_is_attachment_only_false_for_substantive_comment() -> None:
    long_text = "I am writing to express my strong opposition to this proposed rule. " * 3
    assert word_count(long_text) >= 25
    assert is_attachment_only(long_text, min_words=25) is False


def test_submitter_hash_is_case_insensitive_and_deterministic() -> None:
    assert submitter_hash("Jane Doe") == submitter_hash("jane doe")
    assert submitter_hash("Jane Doe") == submitter_hash("  Jane Doe  ")
    assert submitter_hash("Jane Doe") != submitter_hash("John Doe")
