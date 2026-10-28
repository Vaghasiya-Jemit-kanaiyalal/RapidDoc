"""Deterministic keyword extraction for document study aids.

No model is required: the extractor ranks meaningful unigrams and short
phrases from the document's own vocabulary. That keeps the feature available
offline and makes the output reproducible.
"""

import re
from collections import Counter

_STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "also", "am",
    "an", "and", "any", "are", "as", "at", "be", "because", "been", "before",
    "being", "below", "between", "both", "but", "by", "can", "could", "did",
    "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers",
    "herself", "him", "himself", "his", "how", "i", "if", "in", "into", "is",
    "it", "its", "itself", "just", "me", "more", "most", "my", "myself", "no",
    "nor", "not", "now", "of", "off", "on", "once", "only", "or", "other",
    "our", "ours", "ourselves", "out", "over", "own", "same", "she", "should",
    "so", "some", "such", "than", "that", "the", "their", "theirs", "them",
    "themselves", "then", "there", "these", "they", "this", "those", "through",
    "to", "too", "under", "until", "up", "very", "was", "we", "were", "what",
    "when", "where", "which", "while", "who", "whom", "why", "will", "with",
    "would", "you", "your", "yours", "yourself", "yourselves",
    "using", "used", "use", "based", "given", "provided", "according",
    "following", "includes", "include", "included", "describes", "described",
    "document", "documents", "section", "sections", "text", "content",
    "information", "various", "different", "several", "many", "much", "well",
    "able", "need", "needs", "required", "require", "requires", "may", "might",
    "must", "shall", "therefore", "however", "thus", "hence", "moreover",
    "furthermore", "additionally", "overall", "also",
    "make", "makes", "made", "define", "defines", "defined", "improve",
    "improves", "improved", "store", "stores", "stored", "allow", "allows",
    "provide", "provides", "ensure", "ensures", "enable", "enables", "create",
    "creates", "support", "supports", "help", "helps", "faster", "uses",
    "contain", "contains", "contained", "convert", "converts", "converted",
    "produce", "produces", "produced", "absorb", "absorbs", "absorbed",
    "occur", "occurs", "occurred", "fix", "fixes", "fixed", "offer", "offers",
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'\-]*")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def _words(sentence):
    return _WORD_RE.findall(sentence or "")


def _normalized(word):
    word = word.strip("-'").lower()
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("ches", "shes", "xes", "zes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def _candidate_phrases(sentence):
    """Yield runs of content words, stopping at stopwords and punctuation."""
    words = _words(sentence)
    run = []
    for word in words:
        normalized = _normalized(word)
        is_content = len(normalized) >= 3 and normalized not in _STOPWORDS
        if is_content:
            run.append(word)
            continue
        if run:
            yield run
            run = []
    if run:
        yield run


def extract_keywords(text: str, limit: int = 12):
    """Return up to ``limit`` ranked keywords/phrases from ``text``.

    Scores favour repeated terms and multi-word concepts. Proper nouns receive a
    small bonus so names and product terms are not buried under generic nouns.
    """
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 12
    limit = max(1, min(limit, 40))

    cleaned = (text or "").strip()
    if len(cleaned) < 20:
        return []

    counts = Counter()
    display = {}
    proper_bonus = Counter()
    for sentence in _SENTENCE_SPLIT_RE.split(cleaned):
        for run in _candidate_phrases(sentence):
            # Single words are useful; two-word runs capture concepts such as
            # "machine learning" without turning clauses into pseudo-keywords.
            for size in range(1, min(2, len(run)) + 1):
                for start in range(0, len(run) - size + 1):
                    words = run[start:start + size]
                    key = " ".join(_normalized(word) for word in words)
                    if not key or key in _STOPWORDS:
                        continue
                    if size == 1 and len(key) < 3:
                        continue
                    counts[key] += 1
                    display.setdefault(key, " ".join(words))
                    if words[0][:1].isupper():
                        proper_bonus[key] += 1

    ranked = []
    for key, count in counts.items():
        if count < 2 and len(key.split()) == 1:
            # A single mention is usually incidental unless it is a proper noun.
            if proper_bonus[key] == 0:
                continue
        word_count = len(key.split())
        score = count * (1.0 + 0.35 * (word_count - 1))
        if proper_bonus[key]:
            score *= 1.08
        ranked.append((score, count, key, display[key]))

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))

    results = []
    seen = set()
    for _, _, key, shown in ranked:
        if key in seen:
            continue
        # Drop a lower-ranked unigram that is already part of a selected phrase.
        if any(key != other and key in other.split() for other in seen):
            continue
        seen.add(key)
        results.append(shown)
        if len(results) >= limit:
            break
    return results
