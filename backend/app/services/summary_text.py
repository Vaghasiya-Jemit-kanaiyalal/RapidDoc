"""Repair extracted document text before it is summarized.

PDF extraction produces page headers, hard-wrapped lines, split words and
bullets encoded as private-use glyphs. Fed straight into the summarizer, those
become walls of text inside Markdown bullets and can even make the running page
header the document overview. This module reflows the text into logical lines
and gives the summarizer one safe way to turn them into single-line sentences.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, List

from RapidDoc.backend.app.services.document_text import looks_like_code
from RapidDoc.backend.app.services.text_polish import ensure_sentence, split_sentences

# Bullet glyphs seen in PDFs: •, ●, ▪, ◦, ‣, ⁃, ∙, ·, ■, ➤ and the private-use
# glyph Word/PowerPoint exports as a square (U+F0B7).
_BULLET_GLYPHS = "\uf0b7\u2022\u25cf\u25aa\u25e6\u2023\u2043\u2219\u00b7\u25a0\u25a1\u27a4\u27a2"
_BULLET_RE = re.compile(rf"^\s*(?:[-*]|[{re.escape(_BULLET_GLYPHS)}])\s+")
_NUMBERED_ITEM_RE = re.compile(r"^\s*(?:\d{1,3}|[A-Za-z])[.)]\s+")

# Headings that actually occur in reports and practicals. Longest first so
# "problem statement" wins over a shorter prefix.
_CANONICAL_HEADINGS = (
    "conclusion and future work",
    "results and discussion",
    "system architecture",
    "project structure",
    "problem statement",
    "executive summary",
    "learning outcomes",
    "course outcomes",
    "program outcomes",
    "test results",
    "source code",
    "table of contents",
    "future work",
    "bibliography",
    "introduction",
    "background",
    "objectives",
    "objective",
    "methodology",
    "implementation",
    "requirements",
    "architecture",
    "conclusion",
    "conclusions",
    "discussion",
    "evaluation",
    "recommendations",
    "recommendation",
    "performance",
    "challenges",
    "references",
    "appendix",
    "appendices",
    "screenshots",
    "deliverables",
    "procedure",
    "findings",
    "security",
    "analysis",
    "testing",
    "results",
    "summary",
    "output",
    "outputs",
    "design",
    "method",
    "methods",
    "scope",
    "tasks",
    "abstract",
    "appendix",
    "code",
)
_HEADING_SET = frozenset(_CANONICAL_HEADINGS)
_HEADING_PREFIXES = tuple(sorted(_HEADING_SET, key=len, reverse=True))

_METADATA_RE = re.compile(
    r"^(?:subject|course(?:\s+code)?|module(?:\s+code)?|student(?:\s+id|\s+name)?|"
    r"enrol?ment|lecturer|instructor|faculty|department|semester|class|name|date|id)"
    r"\s*[:\-]",
    re.IGNORECASE,
)
_INSTITUTION_RE = re.compile(
    r"\b(?:university|institute|college|department|depstar|faculty|school)\b",
    re.IGNORECASE,
)
_PAGE_NUMBER_RE = re.compile(r"^(?:page\s*)?\d{1,3}$", re.IGNORECASE)
_TITLE_ONLY_RE = re.compile(
    r"^(?:practical|assignment|lab|experiment|exercise)\s*[-:#]?\s*\d+\b",
    re.IGNORECASE,
)
_TEST_LABEL_RE = re.compile(r"^(?:test|step)\s*\d+\b", re.IGNORECASE)
_REVISION_PREFIX_RE = re.compile(r"^(?:new|updated|added|note|todo)\s*[:\-]\s+", re.IGNORECASE)
_URL_OR_CODE_RE = re.compile(r"https?://|\blocalhost\b|\b(?:req|res)\.|=>|[{}]|;\s*$|\u2192", re.IGNORECASE)
_AUX_CAPITAL_RE = re.compile(
    r"\b(were|was|is|are|been|be|has|have|had)\s+"
    r"(Returned|Defined|Replaced|Tested|Connected|Implemented|Created|Used|Added|Removed|"
    r"Updated|Verified|Confirmed|Ensured|Built)\b"
)
_BOX_DRAWING_RE = re.compile(r"[├└│┌┐┘┬┴┼]")
_CODE_FRAGMENT_RE = re.compile(
    r"^(?:[}\])]+|const\s|let\s|var\s|function\s|import\s|export\s|require\(|"
    r"module\.exports|router\.\w|app\.\w|res\.\w|req\.\w|mongoose\.\w|console\.\w)",
    re.IGNORECASE,
)
_SCHEMA_FIELD_RE = re.compile(
    r"[:=]\s*(?:String|Number|Boolean|Date|ObjectId|true|false|null)\b",
    re.IGNORECASE,
)

_OUTCOME_RE = re.compile(
    r"\b(?:successfully|completed|implemented|tested|achieved|confirmed|demonstrated|"
    r"concluded|finally|overall|result|verified|persists?)\b",
    re.IGNORECASE,
)


def _heading_core(line: str) -> str:
    core = re.sub(r"^#{1,6}\s*", "", line.strip())
    core = re.sub(r"^(?:\d{1,3}|[IVXivx]+)[.)]\s*", "", core)
    return core.strip(" \t:.-–—")


def looks_like_heading(line: str) -> bool:
    """True for a short section heading, not for a body sentence that starts
    with the same word ("Objective To connect ..." is body, "Objective" is a
    heading)."""
    stripped = (line or "").strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return True
    if len(stripped) > 100:
        return False
    core = _heading_core(stripped)
    if not core:
        return False
    lowered = re.sub(r"\s+", " ", core.lower())
    if lowered in _HEADING_SET:
        return True
    for heading in _HEADING_PREFIXES:
        if lowered.startswith(heading + " "):
            tail = lowered[len(heading):].strip()
            if len(tail.split()) <= 4 and not re.search(r"[.!?]", tail):
                return True
    return False


def _starts_with_heading(line: str) -> bool:
    """True when a line begins with a heading word followed by a body that
    starts with a capital ("Conclusion In this practical ...")."""
    core = _heading_core(line)
    lowered = core.lower()
    for heading in _HEADING_PREFIXES:
        if lowered == heading:
            return True
        if lowered.startswith(heading + " "):
            rest = core[len(heading):].strip(" :.-–—")
            if rest and rest[:1].isupper():
                return True
    return False


def _looks_like_code_fragment(line: str) -> bool:
    """Catch code that ``looks_like_code`` misses in extracted PDFs.

    Schema bodies arrive as ``title: {`` / ``type: String,`` / ``});`` lines,
    and joining those with prose is what produced the previous gibberish.
    """
    stripped = line.strip()
    if not stripped:
        return False
    if _BOX_DRAWING_RE.search(stripped):
        return True
    if _CODE_FRAGMENT_RE.match(stripped):
        return True
    if stripped.endswith(("{", ";", "=>", ");", "];")):
        return True
    if _SCHEMA_FIELD_RE.search(stripped):
        return True
    if re.match(r"^[\w$]+\s*:\s*[\[{]", stripped):
        return True
    if re.match(r"^[\w$]+\s*:\s*[A-Za-z_'\"\[]", stripped) and len(stripped.split()) <= 6:
        return True
    if re.search(r"\b(?:require\s*\(|module\.exports|console\.log)\b", stripped):
        return True
    return False


def _split_heading_prefix(line: str) -> List[str]:
    """Split ``Conclusion In this practical ...`` into heading + body."""
    core = line.strip()
    for heading in _HEADING_PREFIXES:
        match = re.match(rf"^{re.escape(heading)}\b[\s:.\-–—]+(.+)$", core, re.IGNORECASE)
        if not match:
            continue
        rest = match.group(1).strip()
        if (
            rest[:1].isupper()
            and len(rest.split()) >= 3
            and not re.search(r"https?://|[:{};]", rest)
        ):
            return [heading.title(), rest]
        break
    return [core]


def _furniture_key(line: str) -> str:
    key = re.sub(r"\d+", "#", line.lower())
    return re.sub(r"\s+", " ", key).strip(" .-–—:,")


def _looks_like_repeated_furniture(line: str) -> bool:
    if len(line) > 120:
        return False
    if _INSTITUTION_RE.search(line):
        return True
    if line.isupper() and len(line) <= 80:
        return True
    # Running headers carry a page number at the end ("... 5CSE - 2(C)  9").
    # A digit in the middle is usually a citation ("Shi et al. 2020"), and
    # dropping those lines cut real sentences in half.
    return bool(re.search(r"(?:^|\s)\d{1,4}\s*$", line)) and len(line.split()) <= 12


def _drop_page_furniture(lines: Iterable[str]) -> List[str]:
    materialized = [ln for ln in lines if ln]
    counts = Counter(_furniture_key(ln) for ln in materialized)
    kept: List[str] = []
    for line in lines:
        if not line:
            continue
        if _METADATA_RE.match(line) or _PAGE_NUMBER_RE.fullmatch(line):
            continue
        key = _furniture_key(line)
        if counts.get(key, 0) >= 3 and _looks_like_repeated_furniture(line):
            continue
        kept.append(line)
    return kept


def _drop_short_fragment_runs(lines: List[str]) -> List[str]:
    """Drop vertical/sidebar garbage such as ``B``, ``es``, ``ed``, ``se``.

    A single short fragment can be the tail of a word broken by the page width
    (``Implementatio`` + ``n``), so only runs of two or more are discarded.
    """
    kept: List[str] = []
    run: List[str] = []

    def flush_run() -> None:
        if len(run) < 2:
            kept.extend(run)

    for line in lines:
        if line and len(line) <= 3 and re.fullmatch(r"[A-Za-z]+", line):
            run.append(line)
            continue
        flush_run()
        run = []
        if line:
            kept.append(line)
    flush_run()
    return kept


def _join_lines(previous: str, following: str) -> str:
    if previous.endswith(("-", "\u2010", "\u2011")):
        return previous[:-1] + following.lstrip()

    following = following.strip()
    last_word = previous.split()[-1] if previous.split() else ""
    # A whole line of one or two lowercase letters is the tail of a word broken
    # by the page width ("Implementatio" + "n"). Do not use just the first token:
    # that turned "providing" + "a strong point" into "providinga strong point".
    if (
        len(following) <= 2
        and following.isalpha()
        and following.islower()
        and len(last_word) >= 5
    ):
        return previous + following
    return previous + " " + following


def _should_join(previous: str, following: str) -> bool:
    previous = previous.strip()
    if not previous:
        return True
    if looks_like_heading(previous) and not looks_like_heading(following):
        return False
    if _starts_with_heading(following):
        return False
    if previous.endswith((".", "!", "?", ":", ";", "}", ")", "]")):
        return False
    return True


def _is_drop_fragment(line: str) -> bool:
    stripped = line.strip()
    if not stripped or _PAGE_NUMBER_RE.fullmatch(stripped):
        return True
    return not re.search(r"[A-Za-z]", stripped)


def normalize_extracted_text(text: str) -> str:
    """Reflow extracted text into logical sections/paragraphs.

    Removes repeated page furniture, joins hard-wrapped lines, repairs words
    split across lines, and separates bullets/headings from body text.
    """
    if not text:
        return ""

    raw_lines = [
        re.sub(r"[ \t\u00a0]+", " ", line).strip()
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    lines = _drop_page_furniture(raw_lines)
    lines = _drop_short_fragment_runs(lines)

    logical: List[str] = []
    buffer = ""
    for line in lines:
        if not line:
            continue
        # Drop junk fragments before merging, otherwise "B" + "es" + "ed" turns
        # into "Besed" and gets welded onto the next real sentence.
        if _is_drop_fragment(line):
            continue

        # clean_prose has already removed most code; this catches what it missed
        # and keeps it from being welded onto the next prose sentence.
        if looks_like_code(line) or _looks_like_code_fragment(line):
            if buffer:
                logical.append(buffer)
                buffer = ""
            continue

        if _BULLET_RE.match(line) or _NUMBERED_ITEM_RE.match(line):
            if buffer:
                logical.append(buffer)
            buffer = _NUMBERED_ITEM_RE.sub("", _BULLET_RE.sub("", line)).strip()
            continue

        if not buffer:
            buffer = line
        elif _should_join(buffer, line):
            buffer = _join_lines(buffer, line)
        else:
            logical.append(buffer)
            buffer = line
    if buffer:
        logical.append(buffer)

    output: List[str] = []
    for line in logical:
        for part in _split_heading_prefix(line):
            part = part.strip()
            if not part or _is_drop_fragment(part):
                continue
            output.append(part)
    return "\n\n".join(output)


def clean_inline(text: str) -> str:
    """One safe single-line string for a Markdown bullet or paragraph."""
    text = (text or "").replace("\u00a0", " ")
    text = _BULLET_RE.sub("", text)
    text = _NUMBERED_ITEM_RE.sub("", text)
    text = _REVISION_PREFIX_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = text.replace(" .", ".").replace(" ,", ",")
    # Undo a capital introduced when a PDF wrapped after an auxiliary verb:
    # "validation errors were Returned" -> "... were returned".
    text = _AUX_CAPITAL_RE.sub(lambda m: f"{m.group(1)} {m.group(2).lower()}", text)
    return text.strip(" -–—")


def clean_title(text: str) -> str:
    title = clean_inline(text)
    title = re.sub(r"^#+\s*", "", title)
    title = re.sub(r"[*_`\[\]]", "", title)
    title = re.sub(r"\s+", " ", title).strip(" .:-–—")
    if len(title) > 90:
        title = title[:87].rsplit(" ", 1)[0].rstrip() + "..."
    return title or "Section"


def _is_noise_sentence(sentence: str, skip_titles: bool) -> bool:
    if not sentence:
        return True
    if _METADATA_RE.match(sentence) or re.match(r"^(?:depstar|itue)\b", sentence, re.IGNORECASE):
        return True
    if re.match(r"^Verified in\b", sentence, re.IGNORECASE):
        return True
    if _PAGE_NUMBER_RE.fullmatch(sentence):
        return True
    if len(sentence.split()) < 5:
        return True
    if sentence.strip(" .:-–—").lower() in _HEADING_SET:
        return True
    if skip_titles and (_TITLE_ONLY_RE.match(sentence) or _TEST_LABEL_RE.match(sentence)):
        return True
    if _URL_OR_CODE_RE.search(sentence):
        return True
    return False


def summary_sentences(text: str, skip_titles: bool = False) -> List[str]:
    """Sentences suitable for a summary, one logical line each.

    Newlines/bullets are treated as sentence boundaries, so extracted list items
    do not become one enormous bullet, and every result is single-line.
    """
    out: List[str] = []
    for raw_line in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        line = _BULLET_RE.sub("", line)
        line = _NUMBERED_ITEM_RE.sub("", line)
        line = re.sub(r"\s+", " ", line)
        for piece in split_sentences(line):
            sentence = clean_inline(piece)
            for heading in _HEADING_PREFIXES:
                match = re.match(rf"^{re.escape(heading)}\b[\s:.\-–—]+(.+)$", sentence, re.IGNORECASE)
                if not match:
                    continue
                rest = match.group(1).strip()
                if rest[:1].isupper() and len(rest.split()) >= 4:
                    sentence = rest
                break
            if _is_noise_sentence(sentence, skip_titles):
                continue
            sentence = ensure_sentence(sentence)
            if sentence not in out:
                out.append(sentence)
    return out


def sentence_key(text: str, length: int = 80) -> str:
    """Normalized prefix used for near-duplicate detection."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())[:length]


def is_title_only(text: str) -> bool:
    stripped = clean_inline(text)
    return bool(_TITLE_ONLY_RE.match(stripped)) and len(stripped.split()) <= 16


def is_outcome_sentence(text: str) -> bool:
    return bool(_OUTCOME_RE.search(text))
