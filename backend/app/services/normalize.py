import hashlib
import html
import re

from app.config import get_settings

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_SALUTATION_RE = re.compile(
    r"^\s*(dear\s+[^,\n]{0,60}|to\s+whom\s+it\s+may\s+concern)[,:]\s*",
    re.IGNORECASE,
)
_ATTACHMENT_ONLY_RE = re.compile(
    r"^\s*(please\s+)?see\s+(the\s+)?attach(ed|ment)s?\.?\s*$"
    r"|^\s*(comment|attachment)s?\s+attached\.?\s*$",
    re.IGNORECASE,
)


def clean_text(raw: str) -> str:
    """Strip HTML and collapse whitespace, preserving case for display."""
    without_tags = _HTML_TAG_RE.sub(" ", raw)
    unescaped = html.unescape(without_tags)
    return _WHITESPACE_RE.sub(" ", unescaped).strip()


def normalize_for_hash(text: str) -> str:
    """Lowercase, strip a leading salutation, and collapse whitespace — hashing only."""
    cleaned = clean_text(text).lower()
    without_salutation = _SALUTATION_RE.sub("", cleaned)
    return _WHITESPACE_RE.sub(" ", without_salutation).strip()


def text_hash(normalized: str) -> str:
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def word_count(text: str) -> int:
    return len(text.split())


def is_attachment_only(text: str, min_words: int | None = None) -> bool:
    if min_words is None:
        min_words = get_settings().MIN_WORDS
    normalized = normalize_for_hash(text)
    if not normalized:
        return True
    if _ATTACHMENT_ONLY_RE.match(normalized):
        return True
    return word_count(normalized) < min_words


def submitter_hash(name: str) -> str:
    return hashlib.sha256(name.strip().lower().encode("utf-8")).hexdigest()
