"""Deterministic keyword extraction, no model or network required."""

from RapidDoc.backend.app.services.keyword_extractor import extract_keywords


TEXT = (
    "MongoDB stores documents in collections. A MongoDB schema defines document "
    "fields. Schema design improves MongoDB queries. MongoDB indexing makes "
    "MongoDB queries faster. The task manager uses MongoDB and schema validation. "
    "Indexes support faster queries in MongoDB."
)


def test_keywords_rank_repeated_terms_and_keep_phrases_short():
    keywords = extract_keywords(TEXT, 12)

    assert keywords[0] == "MongoDB"
    assert "MongoDB queries" in keywords
    assert all(len(term.split()) <= 2 for term in keywords)
    assert "makes" not in " ".join(keyword.lower() for keyword in keywords)


def test_keyword_limit_and_short_text():
    assert len(extract_keywords(TEXT, 3)) <= 3
    assert extract_keywords("Too short to rank.", 10) == []
