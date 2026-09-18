"""Turn an arbitrary article's text into a short search query.

The live retrieval pipeline (retrieval/gdelt.py) needs *search terms*, not
the whole article, to query GDELT. Uses YAKE — a lightweight, unsupervised
keyphrase extractor with no model download and no network call — so this
works instantly on any pasted text or fetched-article title.
"""

import yake

# top_n small on purpose: GDELT's query syntax ANDs bare terms together, so
# too many terms over-constrains the search and returns nothing. 6 keyphrases
# joined with OR-ish breadth (see build_query) works well in practice.
_extractor = yake.KeywordExtractor(lan="en", n=3, top=6, dedupLim=0.7)


def extract_keywords(text: str, max_chars: int = 2000) -> list[str]:
    """Return up to 6 representative keyphrases from `text`, ranked by
    YAKE's score (lower score = more representative, so we sort ascending)."""
    if not text or not text.strip():
        return []
    snippet = text[:max_chars]
    scored = _extractor.extract_keywords(snippet)
    return [kw for kw, _score in sorted(scored, key=lambda pair: pair[1])]


def build_gdelt_query(text: str) -> str:
    """Build a GDELT DOC 2.0 `query` param from article text: the top few
    keyphrases quoted and OR'd together, so the search is broad enough to
    surface reworded copies of the same story rather than requiring every
    term to match verbatim."""
    keywords = extract_keywords(text)
    if not keywords:
        # fall back to the first few words of the raw text
        words = text.strip().split()[:6]
        return " ".join(words)
    quoted = [f'"{kw}"' if " " in kw else kw for kw in keywords[:5]]
    return " OR ".join(quoted)
