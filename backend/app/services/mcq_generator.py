"""Deterministic, varied MCQ generation from a document's own text.

The local MCQ brain is a BART model fine-tuned on RACE, a reading-comprehension
dataset whose questions are overwhelmingly of two forms: "which of the following
is NOT mentioned..." and "which statement is NOT true...". Asking it for a quiz
therefore produced five near-identical negative questions, distractors lifted
from other documents, and the occasional option that was itself a question
("What is the main purpose of the research paper?" as an answer choice).

A small fine-tuned model cannot be talked out of its training distribution with
a better prompt. This module sidesteps it: it reads the document, pulls real
facts out of it, and writes questions from templates, using the document's own
vocabulary to build plausible wrong answers. Nothing is invented, so every
question is answerable from the text and every distractor is at least topical.

The generators below each target a different cognitive level, which is what
makes the resulting quiz varied:

* ``definition`` - what does the document call this thing? (terminology)
* ``purpose``    - why is X done? (reasoning about intent)
* ``cause``      - what follows from / because of X? (causal reasoning)
* ``numeric``    - what figure does the document give? (data recall)
* ``statement``  - which statement about the document is true? (verification)

Every generator is deliberately built from a *complete sentence*. Hard-wrapped
PDF lines and half-sentences are rejected before they reach a template, because
a quiz made of line fragments teaches nothing. There is no fill-in-the-blank
generator: a blank in the middle of an extracted line is exactly the failure
mode this module is meant to avoid.

:func:`build_mcq_set` interleaves the generators so a request for five questions
produces five different kinds rather than five of the easiest kind.
"""

import re

__all__ = ["build_mcq_set", "QUESTION_TYPES"]

QUESTION_TYPES = (
    "definition",
    "purpose",
    "cause",
    "numeric",
    "statement",
)

# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[A-Za-z][\w'-]*")

# Words too common to make a useful distractor: "the document states that the
# system was used" is not a plausible wrong answer to anything.
_STOPWORDS = frozenset("""
a an the and or but if then than that this these those there here it its it's
is are was were be been being am do does did done have has had having will
would shall should can could may might must of in on at to for from by with
without about into over under again further once all any both each few more
most other some such no nor not only own same so too very s t just don now
as also which who whom whose what when where why how between during before
after above below up down out off because while since until against
we us our you your i me my mine he him his she her they them their
document documents paper papers study studies research section text passage
according mentioned states stated describes described says say says note notes
following given provides provided based used using one two three
four five six seven eight nine ten
""".split())

# Verbs, adverbs and vague words. These must never be an answer: "which is
# connected with Props - Pass or React?" is not a question worth asking.
_WEAK_WORDS = frozenset("""
create created creating adds added adding use used using uses run runs running
write writes writing written build builds building made make makes making
include includes including included require requires required requireing
pass passes passing passsed passsed sent send sends sent set sets setting
must should shall will would can could may might need needs needed
structure structured structuring compose composed composing duplicate
duplicated get gets getting got check checks checked checking run ran
bundle bundled successfully successfully successful success result results
resulting lead leads led cause causes caused follow follows followed
through above below between within without across during before after
well good better best first second third next last final finally
new old good also only just even still already always never often sometimes
like unlike same different various several many few more most less least
practical objective conclusion project structure implementation component
components page pages document text line lines word words time times
box image object request requests edit editing label labels
approximately corresponding along alongside
""".split())

# Verbs and structures that make a good "definition" cue. A colon is not a
# definition: PDF line wrapping produced ``document-`` and the old colon pattern
# happily asked students to identify that fragment.
_DEFINITION_PATTERNS = (
    re.compile(
        r"^(?P<term>[A-Z][\w \-]{2,50}?)\s+(?:is|are)\s+"
        r"(?:defined|described|known|referred\s+to|called|termed)\s+as\s+"
        r"(?P<def>.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<term>[A-Z][\w \-]{2,50}?)\s+(?:refers\s+to|means|denotes)\s+"
        r"(?P<def>.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<term>[A-Z][\w \-]{2,50}?)\s+(?:is|are)\s+"
        r"(?P<def>(?:a|an|the)\s+.+)$",
        re.IGNORECASE,
    ),
)

_PURPOSE_RE = re.compile(
    r"(?P<subj>(?:the|a|an)\s+[A-Za-z][\w-]*"
    r"(?:\s+(?!(?:that|which|is|are|was|were)\b)[A-Za-z][\w-]*){0,7})"
    r"\s+(?:that\s+)?(?:is|are|was|were)\s+"
    r"(?:used|designed|intended|employed|adopted|created|developed|built)\s+"
    r"(?:to|in\s+order\s+to)\s+(?P<purp>.+)$",
    re.IGNORECASE,
)

_CAUSE_RE = re.compile(
    r"^(?:because|since|as|due\s+to|owing\s+to|thanks\s+to|on\s+account\s+of)\s+"
    r"(?P<cause>.+?),\s*(?P<effect>.+)$",
    re.IGNORECASE,
)
_EFFECT_RE = re.compile(
    r"^(?P<cause>.{15,140}?)\s*,?\s+(?:which\s+)?"
    r"(?:leads?\s+to|led\s+to|results?\s+in|resulted\s+in|"
    r"resulting\s+in|gives?\s+rise\s+to|gave\s+rise\s+to|"
    r"causes?|caused)\s+(?P<effect>.+)$",
    re.IGNORECASE,
)

_NUMBER_RE = re.compile(
    r"(?P<value>\b\d[\d,]*(?:\.\d+)?(?:\s*[-–]\s*\d[\d,]*(?:\.\d+)?)?\s*"
    r"(?:%|percent|per\s+cent|[KkMmBb](?![A-Za-z])|thousand|million|billion|lakh|crore)?)",
    re.IGNORECASE,
)

# An option that is itself a question is never a valid answer choice; the BART
# brain produced these ("What is the main purpose of the research paper?").
_QUESTION_LIKE = re.compile(r"^(what|which|who|whom|whose|when|where|why|how|is|are|was|were|do|does|did|can|could|should|will|would)\b", re.IGNORECASE)
_ASKING = re.compile(r"\?\s*$")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


# A report's table cells split sentences across rows, so a line can end on a word
# that promises a continuation. Left alone this produced stems like
# "Objective To set up a ____ development environment using Vite and build a
# static UI using" - the blank landed where the sentence had not finished.
_DANGLING_TAIL = frozenset("""
a an the and or but so of in on at to for from by with without into onto over
under through between among across per via than then that which who whom whose
when where while because since although though if unless until as is are was
were be been being am has have had do does did will would shall should can could
may might must its their our your my this these those such other another each
every some any both either neither also plus versus vs using use used include
including add adding based
""".split())

# The label cell of a table row arrives glued to the first line of its value:
# "Objective To set up a React development environment...". These are the labels
# AWDF-style reports actually use, so they are listed rather than guessed at.
_ROW_LABEL = re.compile(
    r"^(?:objective|aim|goal|task|requirement|requirements|deliverable|deliverables|"
    r"problem|problem\s+statement|statement|pre-?requirement|pre-?requisite|"
    r"technology|note|note\s+s|about|background|context|summary|result|results|"
    r"conclusion|introduction|description|instruction|instructions|step|steps)\s+",
    re.IGNORECASE,
)


def _strip_row_label(sentence: str) -> str:
    """Remove a leading table-label word from the front of a sentence."""
    stripped = _ROW_LABEL.match(sentence or "")
    if not stripped:
        return sentence
    rest = sentence[stripped.end():]
    # Only drop the label when real prose follows, never when that would empty
    # the sentence or leave a fragment.
    return rest if len(rest.split()) >= 5 else sentence


def _join_continuations(lines: list) -> list:
    """Re-attach a line that stops on a word demanding a continuation.

    Only a dangling final word triggers the join. Joining every unterminated line
    would weld a page footer onto the first heading of the next block, because
    furniture lines also lack a full stop. A blank line ends the paragraph and
    cancels the join.
    """
    joined = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            joined.append(line)
            continue

        # The nearest preceding non-blank line inside the same paragraph.
        previous = None
        index = None
        for i in range(len(joined) - 1, -1, -1):
            if joined[i].strip():
                previous, index = joined[i].strip(), i
                break
            break  # a blank line ends the paragraph

        if previous and index is not None:
            last = previous.split()[-1].lower().strip(".,;:()[]")
            if (
                last in _DANGLING_TAIL
                and not _is_code_like(previous)
                and not _is_code_like(stripped)
            ):
                joined[index] = f"{joined[index].rstrip()} {stripped}"
                continue

        joined.append(line)
    return joined


# Source lines that are code, shell commands or file trees. They are excellent
# material for a code slide and useless as quiz content, and left in the pool
# they produce questions like "Which is NOT a command: src/ or Vite?".
_CODE_LINE = re.compile(
    r"(^\s*[└├│]|^\s*\$|^\s*npm |^\s*npx |^\s*yarn |^\s*cd |^\s*git |"
    r"[\w-]+\.(?:jsx?|tsx?|py|json|html|css|md|csv|pdf|docx)\b|"
    r"^\s*[\)\]\}]|=>|;\s*$|\{\s*$)",
    re.IGNORECASE,
)


def _is_code_like(line: str) -> bool:
    text = line.strip()
    if not text:
        return True
    if _CODE_LINE.search(text):
        return True
    # A line that is mostly punctuation is a code fragment, not a sentence.
    words = text.split()
    alpha = sum(1 for w in words if any(c.isalpha() for c in w))
    return bool(words) and alpha / len(words) < 0.7


def sentences_of(text: str, min_words: int = 6, max_words: int = 90) -> list:
    """Split a block of text into usable, quiz-worthy sentences in document order.

    Code, shell commands and file-tree lines are dropped: they make nonsense
    questions and distractors.
    """
    out = []
    for line in _join_continuations((text or "").split("\n")):
        for raw in _SENTENCE_SPLIT.split(line):
            s = _strip_row_label(_clean(raw))
            words = s.split()
            if not (min_words <= len(words) <= max_words):
                continue
            if _is_code_like(s):
                continue
            out.append(s)
    return out


# A complete sentence is the difference between a quiz and a wall of PDF line
# fragments. These checks are deliberately conservative: a question built from
# a fragment is worse than one fewer question.
_BAD_SENTENCE_START = re.compile(
    r"^(?:and|but|or|which|who|whom|whose|where|when|while|because|although|"
    r"though|if|unless|until|then|thus|hence|also|however|moreover|"
    r"furthermore|of|on|for|from|with|without)\b",
    re.IGNORECASE,
)
_BAD_SENTENCE_CONTENT = re.compile(
    r"\b(?:figure|table|algorithm|copyright|conference|proceedings|university|"
    r"college|department|inc\.|ltd\.|et\s+al\.?|https?://|www\.|arxiv|"
    r"preprint|accepted|submitted|"
    # Known artefacts of re-joining a hyphenated PDF line after citation
    # removal. Rejecting the whole sentence is safer than asking a quiz about
    # "image edita different approach".
    r"edita|reprethe|localizationaware|documentedit|providinga|usedby)\b",
    re.IGNORECASE,
)
_FINITE_VERB_RE = re.compile(
    r"\b(?:is|are|was|were|be|been|being|has|have|had|do|does|did|can|could|"
    r"may|might|must|shall|should|will|would)\b",
    re.IGNORECASE,
)
_BASE_VERBS = frozenset("""
accept achieve add allow analyse analyze apply approach argue assess attend become
begin build calculate capture classify collect combine compare comprise contain
copy create curate define demonstrate describe design detect develop discuss edit
enable evaluate examine explain extract find focus form generate give ground
identify improve include increase investigate introduce lead localize make map
measure mention model modify move need obtain offer outperform perform predict
present produce propose provide recognise recognize reduce refer remain remove
replace represent require result retrieve show simulate split store suggest
support take test train translate understand use utilize validate work
""".split())
_DANGLING_END = frozenset("""
a an the and or but so of in on at to for from by with without into onto over
under through between among across per via than then that which who whom whose
when where while because since although though if unless until as plus versus
vs using include including add adding based
""".split())


def _has_finite_predicate(text: str) -> bool:
    lowered = text.lower()
    if _FINITE_VERB_RE.search(lowered):
        return True
    for token in _WORD.findall(lowered):
        forms = {token}
        if token.endswith("ing"):
            forms.update({token[:-3], token[:-3] + "e"})
        if token.endswith("ed"):
            forms.update({token[:-2], token[:-1]})
        if token.endswith("es"):
            forms.add(token[:-2])
        if token.endswith("s"):
            forms.add(token[:-1])
        if forms & _BASE_VERBS:
            return True
        if len(token) >= 5 and token.endswith("ed") and token not in {
            "hundred", "indeed", "embed", "red", "seed",
        }:
            return True
    return False


def _is_complete_sentence(sentence: str) -> bool:
    """Reject PDF fragments, captions, author lines and unfinished clauses."""
    text = _clean(sentence)
    if not text:
        return False
    words = text.split()
    if not (7 <= len(words) <= 70):
        return False
    if not text[:1].isupper():
        return False
    if not re.search(r"[.!?][\"')\]]?$", text):
        return False
    if _BAD_SENTENCE_START.match(text) or _BAD_SENTENCE_CONTENT.search(text):
        return False
    if "@" in text:
        return False
    if text.count("(") != text.count(")") or text.count("[") != text.count("]"):
        return False
    if text.endswith(("-", "–", "—", ",", ";", ":")):
        return False
    if re.search(r"\bto,\s+[a-z]", text):
        return False
    last = text.rstrip("\"'”’)]}.").split()[-1].lower()
    if last in _DANGLING_END:
        return False
    if _is_code_like(text):
        return False
    return _has_finite_predicate(text)


def _content_words(sentence: str) -> list:
    """Distinctive words of a sentence, usable as answer candidates or distractors.

    Stopwords and generic verbs are dropped here rather than in each caller: a
    distractor like "Least" or "Include" is worse than no question at all.
    """
    out = []
    for m in _WORD.finditer(sentence):
        w = m.group(0).lower()
        if w in _STOPWORDS or w in _WEAK_WORDS or len(w) < 4 or w.isdigit():
            continue
        if _is_code_like(m.group(0)):
            continue
        if w not in out:
            out.append(w)
    return out


def _key_terms(text: str, limit: int = 40) -> list:
    """The document's characteristic vocabulary, most distinctive first.

    Frequency alone favours boilerplate, so terms are scored by frequency and
    boosted when they look like proper nouns or multi-word technical phrases -
    exactly the things worth asking about.
    """
    counts = {}
    displays = {}
    for m in _WORD.finditer(text or ""):
        w = m.group(0)
        low = w.lower()
        if low in _STOPWORDS or low in _WEAK_WORDS or len(low) < 3 or low.isdigit():
            continue
        counts[low] = counts.get(low, 0) + 1
        # Keep the document's own casing: "DocEdit" must not become "Docedit".
        displays.setdefault(low, w)

    phrases = {}
    phrase_displays = {}
    # Only spaces join a multi-word phrase - letting \s match a newline welded
    # the end of one cell onto the start of the next ("Component Architecture\nObjective").
    for m in re.finditer(r"\b([A-Z][\w-]{2,}(?:[ ][A-Z][\w-]{2,}){0,2})\b", text or ""):
        p = m.group(1).strip()
        if p.lower() not in _STOPWORDS and not _is_code_like(p):
            # Key on the lowercase form so a phrase and the same word counted
            # individually do not both enter the pool as near-duplicate options.
            key = p.lower()
            phrases[key] = phrases.get(key, 0) + 1
            phrase_displays.setdefault(key, p)
            if key not in counts:
                counts[key] = 0
                displays.setdefault(key, p)

    scored = []
    for word, n in counts.items():
        if _is_code_like(word):
            continue
        display = displays.get(word, word)
        bonus = 1.6 if display[:1].isupper() else 1.0
        scored.append((n * bonus, display, word))
    for phrase, n in phrases.items():
        if n <= 0:
            continue
        scored.append((n * 2.0, phrase_displays.get(phrase, phrase), phrase))

    scored.sort(key=lambda x: (-x[0], x[1]))
    out = []
    seen = set()
    for _s, display, key in scored:
        if key in seen:
            continue
        seen.add(key)
        out.append(display)
        if len(out) >= limit:
            break
    return out


_GENERIC_SINGLE_TERMS = frozenset("""
task tasks tool tools user users system systems model models work works document
documents paper papers dataset datasets data approach approaches method methods
result results way ways thing things part parts type types example examples
information process processes feature features application applications
box image object request requests edit editing label labels text
command commands visual textual spatial bounding loss roi
accurate ambiguous public available proposed corresponding strong
learning vision recognition graph graphs
""".split())


def _plausible_option(text: str, max_words: int = 22) -> bool:
    """Reject options that cannot serve as an answer choice."""
    text = _clean(text)
    if len(text) < 2 or len(text.split()) > max_words:
        return False
    if _ASKING.search(text) or _QUESTION_LIKE.match(text):
        return False
    if re.search(r"\d", text):
        return True
    if text.count("(") != text.count(")") or text.count("[") != text.count("]"):
        return False
    if text.endswith(("-", "–", "—", ",", ";", ":")):
        return False
    last = text.rstrip("\"'”’)]}.").split()[-1].lower()
    if last in _DANGLING_END:
        return False
    # Needs at least one real word.
    return any(w.lower() not in _STOPWORDS and len(w) > 1 for w in _WORD.findall(text))


def _looks_sentence(text: str) -> bool:
    text = _clean(text)
    return len(text.split()) >= 8 or bool(re.search(r"[.!?][\"')\]]?$", text))


def _display_option(text: str) -> str:
    """Give every option a consistent, presentable first letter."""
    text = _clean(text).strip(" -–—")
    if text[:1].islower():
        text = text[:1].upper() + text[1:]
    return text


def _pick_distractors(
    answer: str,
    pool: list,
    need: int,
    seed_terms: list = None,
    max_words: int = 22,
    sentence_mode: bool = None,
) -> list:
    """Choose wrong options that are topical but not the answer.

    The answer's own words are excluded so an option cannot be accidentally
    correct as well, and an option already present is never repeated. Short
    term answers only receive short term options; full-sentence answers receive
    full-sentence options, so a quiz never offers three sentences and a noun.
    """
    answer_words = {w.lower() for w in _WORD.findall(answer)}
    answer_norm = _normalize_option(answer)
    answer_is_sentence = _looks_sentence(answer) if sentence_mode is None else sentence_mode
    chosen = []
    seen = {answer_norm}
    for candidate in pool or []:
        if len(chosen) >= need:
            break
        text = _clean(candidate)
        if not _plausible_option(text, max_words=max_words):
            continue
        if _looks_sentence(text) != answer_is_sentence:
            continue
        norm = _normalize_option(text)
        if not norm or norm in seen:
            continue
        if norm in answer_norm or answer_norm in norm:
            continue
        if not answer_is_sentence and len(text.split()) == 1 and norm in _GENERIC_SINGLE_TERMS:
            continue
        words = {w.lower() for w in _WORD.findall(text)}
        if not words and not re.search(r"\d", text):
            continue
        # Too much overlap with the answer means it could also be correct.
        if words and answer_words and len(words & answer_words) / len(words) > 0.8:
            continue
        seen.add(norm)
        chosen.append(text)
    return chosen


def _normalize_option(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _shuffle_with_answer(options: list, answer_text: str, rotate: int):
    """Place the answer at a rotating position.

    Always putting the correct answer in slot A is a real flaw in a generated
    quiz - a student can score full marks by answering "A" every time.
    """
    if not options or answer_text is None:
        return list(options), None
    try:
        idx = options.index(answer_text)
    except ValueError:
        return list(options), None

    target = rotate % len(options)
    if idx != target:
        options = list(options)
        options.insert(target, options.pop(idx))
    return options, chr(ord("A") + target)


# ---------------------------------------------------------------------------
# Question generators. Each returns a full question dict or None.
# ---------------------------------------------------------------------------

def _q(stem: str, answer: str, distractors: list, kind: str, source: str) -> dict:
    return {
        "question": stem,
        "answer_text": answer,
        "distractors": distractors,
        "type": kind,
        "source": source,
    }


_TITLE_LIKE = re.compile(r"^[^:\n]{1,60}(?::|\s[-–—]\s)\s*\S")


# An instruction, not a subject. "Create" opened a sentence in most practical
# reports, so the question became '...connected with "Create"?', which no
# student could answer from the document.
_IMPERATIVE_VERBS = frozenset("""
create add build write implement design develop set use ensure define run
install configure generate perform apply display print include initialize make
take give allow provide check select choose insert update remove delete replace
compose render draw show list load save open close start stop
""".split())


def _usable_cue(candidate: str, start: int, all_text: str) -> bool:
    """Whether a capitalised word can be the subject of an association question."""
    text = candidate.strip()
    if not text:
        return False
    # A shouted logo or institution mark carries nothing worth being asked about.
    if text.isupper() and len(text) > 3:
        return False
    if start == 0 and text.lower() in _IMPERATIVE_VERBS:
        return False
    # A name used exactly once is an author's name or a stray proper noun, not a
    # concept the document develops.
    if " " not in text and all_text.count(text.lower()) < 2:
        return False
    return True


def _is_title_like(sent: str) -> bool:
    """A heading is not quiz material - blanking a word out of one is nonsense."""
    return bool(_TITLE_LIKE.match(sent))


def _term_like(text: str, max_words: int = 6) -> bool:
    """Whether a string is a short concept, not a sentence fragment."""
    text = _clean(text)
    if not text or len(text.split()) > max_words:
        return False
    if not _plausible_option(text, max_words=max_words):
        return False
    if _looks_sentence(text) or _is_code_like(text):
        return False
    words = _WORD.findall(text)
    if not words:
        return False
    if len(words) == 1:
        word = words[0].lower()
        if word in _GENERIC_SINGLE_TERMS or word in _WEAK_WORDS:
            return False
        # A bare verb ("curate", "contains") makes a nonsense option and a
        # nonsense statement target. Strip common inflections before checking.
        forms = {word}
        for suffix, stems in (
            ("ing", (word[:-3], word[:-3] + "e")),
            ("ed", (word[:-2], word[:-1])),
            ("es", (word[:-2],)),
            ("s", (word[:-1],)),
        ):
            if word.endswith(suffix):
                forms.update(stems)
        if forms & _BASE_VERBS:
            return False
    return True


def _meaningful_term(text: str, max_words: int = 4) -> bool:
    if not _term_like(text, max_words=max_words):
        return False
    words = _WORD.findall(text)
    return len(words) > 1 or (bool(words) and len(words[0]) >= 5)


def _nounish_term(text: str, max_words: int = 4) -> bool:
    """Reject adjectives and participles that read badly as a named option."""
    if not _meaningful_term(text, max_words=max_words):
        return False
    words = _WORD.findall(text)
    if len(words) == 1:
        word = words[0].lower()
        if word.endswith(("-based", "-aware", "ous", "ive", "able", "ible", "ic")):
            return False
    return True


def _is_good_cue(text: str, all_text: str) -> bool:
    """Whether a proper noun / phrase is worth attaching a question to."""
    text = _clean(text)
    if not _meaningful_term(text, max_words=5):
        return False
    if text.lower() in _IMPERATIVE_VERBS:
        return False
    if text.isupper() and len(text) > 3:
        return False
    if " " not in text:
        # A lowercase common word ("edit") is not a concept worth naming.
        if not text[:1].isupper():
            return False
        if all_text.lower().count(text.lower()) < 2:
            camel_case = any(c.isupper() for c in text[1:])
            if not camel_case and len(text) < 8:
                return False
    return True


def _shorten(text: str, limit: int) -> str:
    """Trim on a word boundary so a stem never ends mid-word."""
    text = _clean(text)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-–—")
    return (cut or text[:limit]) + "…"


def _clause_like(text: str) -> bool:
    text = _clean(text).rstrip(".")
    if not (3 <= len(text.split()) <= 24):
        return False
    return _plausible_option(text, max_words=28) and not _is_title_like(text)


def _effect_clauses(sentences) -> list:
    """Complete consequence clauses from the document's causal sentences."""
    out = []
    for sent in sentences:
        for pattern in (_EFFECT_RE, _CAUSE_RE):
            match = pattern.match(sent)
            if not match:
                continue
            clause = _clean(match.group("effect")).rstrip(".")
            if _clause_like(clause):
                out.append(clause)
    return out


def _purpose_phrases(sentences) -> list:
    """Verb phrases that can answer "what is X used to do?"."""
    out = []
    for sent in sentences:
        for match in re.finditer(
            r"\b(?:to|in\s+order\s+to)\s+(?P<phrase>[a-z][^.;]{8,90})",
            sent,
            re.IGNORECASE,
        ):
            phrase = _clean(match.group("phrase")).rstrip(".")
            first = (_WORD.findall(phrase) or [""])[0].lower()
            if first not in _BASE_VERBS:
                continue
            if not (3 <= len(phrase.split()) <= 20):
                continue
            if _plausible_option(phrase, max_words=22) and not _is_title_like(phrase):
                out.append(phrase)
    return out


def _number_and_unit(sent: str, match) -> tuple:
    """Return a numeric value and the noun it measures, when one is present."""
    value = _clean(match.group("value"))
    tail = sent[match.end():]
    unit = ""
    unit_match = re.match(
        r"\s+(?P<unit>[A-Za-z][A-Za-z-]*(?:\s+[A-Za-z][A-Za-z-]*){0,2})",
        tail,
    )
    if unit_match:
        unit = _clean(unit_match.group("unit"))
        if re.match(r"^of\s+", unit, re.IGNORECASE):
            unit = re.sub(r"^of\s+", "", unit, flags=re.IGNORECASE)
        if re.search(r"\s+of\s+", unit, re.IGNORECASE):
            unit = re.split(r"\s+of\s+", unit, maxsplit=1, flags=re.IGNORECASE)[0]
        parts = unit.split()
        while parts and parts[-1].lower() in {
            "and", "or", "with", "along", "from", "for", "to", "in", "on",
            "by", "at", "as", "which", "that", "were", "was", "are", "is",
            "the", "a", "an",
        }:
            parts.pop()
        unit = " ".join(parts)
    return value, unit


def _numeric_variants(value: str, unit: str = "") -> list:
    """Plausible wrong figures, preserving the unit and suffix."""
    text = _clean(value).replace(" ", "")
    if "%" in text:
        numbers = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]
        if not numbers:
            return []
        base = numbers[0]
        span = numbers[1] - base if len(numbers) > 1 else 0
        out = []
        for delta in (-7, -4, 4, 7, 10):
            low = max(1, base + delta)
            if span:
                out.append(f"{low:g}-{low + span:g}%")
            else:
                out.append(f"{low:g}%")
        return out

    parsed = re.match(
        r"^(?P<num>[\d,.]+)(?P<suffix>[KkMmBb]|thousand|million|billion)?$",
        text,
    )
    if not parsed:
        return []
    try:
        number = float(parsed.group("num").replace(",", ""))
    except ValueError:
        return []
    suffix = parsed.group("suffix") or ""
    if not suffix and 1900 <= number <= 2100:
        variants = [number - 1, number + 1, number + 2, number + 3]
    elif not suffix:
        variants = [number * 2, number * 3, number / 2, number + 5]
    else:
        variants = [number * 2, number * 3, number / 2, number * 1.5]
    out = [f"{v:g}{suffix}" for v in variants if v > 0]
    if unit:
        out = [f"{v} {unit}" for v in out]
    return out


def gen_association(sentences, terms, vocabulary, rotate):
    """"Which of these does the document develop alongside X?"

    The answer is a substantive term that genuinely appears in the same
    sentence; generic words such as "task", "tool" and "model" are rejected, so
    the question asks about a concept rather than a stray noun.
    """
    all_text = " ".join(sentences)
    meaningful = [t for t in terms if _meaningful_term(t, max_words=4)]
    for idx, sent in enumerate(sentences):
        if _is_title_like(sent):
            continue
        sent_terms = [t for t in meaningful if t.lower() in sent.lower()]
        if len(sent_terms) < 2:
            continue
        cue = next(
            (t for t in sent_terms if _is_good_cue(t, all_text)),
            None,
        )
        if not cue:
            continue

        candidates = []
        for term in sent_terms:
            if _normalize_option(term) == _normalize_option(cue):
                continue
            if not _meaningful_term(term, max_words=4):
                continue
            candidates.append(term)
        if not candidates:
            continue
        # Prefer a multi-word technical phrase, then a proper noun.
        answer = max(candidates, key=lambda t: (len(t.split()) > 1, t[:1].isupper(), len(t)))

        pool = []
        for j, other in enumerate(sentences):
            if j == idx:
                continue
            for term in meaningful:
                if term.lower() in other.lower():
                    pool.append(term)
        distractors = _pick_distractors(
            answer, pool, 3, max_words=4, sentence_mode=False)
        if len(distractors) < 3:
            continue
        return _q(
            f'According to the document, which of the following is most closely '
            f'associated with "{cue}"?',
            answer, distractors[:3], "association", sent)
    return None


def gen_definition(sentences, terms, vocabulary, rotate):
    """"According to the document, what is <term>?" - terminology questions."""
    generic_terms = {
        "the model", "the system", "the document", "this model", "this system",
        "the paper", "the dataset", "the approach", "the method",
        "our dataset", "our model", "our proposed model", "our work",
        "this dataset", "this work", "the proposed dataset",
        "the proposed model", "the new dataset", "the new model",
    }

    def make_question(term, definition, source):
        term = _clean(term)
        if term.lower().startswith("the "):
            term = term[4:].strip()
        definition = _clean(definition).rstrip(".")
        if not _nounish_term(term, max_words=6):
            return None
        if term.lower() in generic_terms:
            return None
        if not (5 <= len(definition.split()) <= 30):
            return None
        if _BAD_SENTENCE_CONTENT.search(definition) or _is_code_like(definition):
            return None
        if definition.endswith(("-", "–", "—", ",", ";", ":")):
            return None
        pool = [
            t for t in terms
            if _nounish_term(t, max_words=6)
            and _normalize_option(t) != _normalize_option(term)
        ]
        # Prefer named entities and technical phrases over common nouns.
        pool.sort(
            key=lambda t: (t[:1].isupper(), len(t.split()) > 1, len(t)),
            reverse=True,
        )
        distractors = _pick_distractors(
            term, pool, 3, max_words=6, sentence_mode=False)
        if len(distractors) < 3:
            return None
        return _q(
            f'According to the document, which term is described as '
            f'"{_shorten(definition, 150)}"?',
            term, distractors[:3], "definition", source)

    for sent in sentences:
        # A heading like "Practical 1: Introduction to React" is not a
        # definition; matching it produced a question that only restated the
        # document's own title.
        if _is_title_like(sent):
            continue
        for pattern in _DEFINITION_PATTERNS:
            m = pattern.match(sent)
            if not m:
                continue
            question = make_question(m.group("term"), m.group("def"), sent)
            if question:
                return question

        # Appositive definitions: "DocEditor, a Transformer-based model ..."
        # or "the DocEdit dataset, a collection of ...". These are common in
        # papers and are more reliable than a regex that hunts for "is a".
        appositive = re.search(
            r"\b(?P<term>(?:[Tt]he\s+)?[A-Z][\w-]*"
            r"(?:\s+[a-z][\w-]*){0,3})\s*,\s*"
            r"(?P<def>(?:a|an|the)\s+[^.;]{25,220})",
            sent,
        )
        if appositive:
            question = make_question(
                appositive.group("term"), appositive.group("def"), sent)
            if question:
                return question
    return None


def gen_purpose(sentences, terms, vocabulary, rotate):
    """"Why is X done?" - intent questions from 'is used to' structures."""
    purpose_pool = _purpose_phrases(sentences)
    for sent in sentences:
        m = _PURPOSE_RE.search(sent)
        if not m:
            continue
        subject = _clean(m.group("subj"))
        purpose = _clean(m.group("purp")).rstrip(".")
        if not _term_like(subject, max_words=8):
            continue
        if not _clause_like(purpose):
            continue
        distractors = _pick_distractors(
            purpose, purpose_pool, 3, max_words=24, sentence_mode=False)
        if len(distractors) < 3:
            continue
        # "what is The retrieval module" reads like a typo; lower an introductory
        # article when the subject moves into the middle of the stem.
        first, _, rest = subject.partition(" ")
        if first.lower() in {"the", "a", "an"}:
            subject = f"{first.lower()} {rest}".strip()
        return _q(
            f"According to the document, what is {subject} used to do?",
            purpose, distractors[:3], "purpose", sent)
    return None


def gen_cause(sentences, terms, vocabulary, rotate):
    """Cause/effect questions, from both 'because' and 'leads to' phrasing."""
    effect_pool = _effect_clauses(sentences)
    for sent in sentences:
        for pattern in (_EFFECT_RE, _CAUSE_RE):
            m = pattern.match(sent)
            if not m:
                continue
            cause = _clean(m.group("cause"))
            effect = _clean(m.group("effect")).rstrip(".")
            if not _clause_like(cause) or not _clause_like(effect):
                continue
            distractors = _pick_distractors(
                effect, effect_pool, 3, max_words=26, sentence_mode=False)
            if len(distractors) < 3:
                continue
            return _q(
                f'According to the document, what follows from '
                f'"{_shorten(cause, 120)}"?',
                effect, distractors[:3], "cause", sent)
    return None


def _numeric_pool(sentences) -> list:
    out = []
    for sent in sentences:
        for match in _NUMBER_RE.finditer(sent):
            value, unit = _number_and_unit(sent, match)
            if not value:
                continue
            display = value if "%" in value else f"{value} {unit}".strip()
            if display:
                out.append(display)
    return out


def gen_numeric(sentences, terms, vocabulary, rotate):
    """Figure recall: "How many ... does the document mention?"."""
    numeric_pool = _numeric_pool(sentences)
    for sent in sentences:
        for m in _NUMBER_RE.finditer(sent):
            value, unit = _number_and_unit(sent, m)
            if len(value) < 2:
                continue
            is_percent = "%" in value
            if not unit and not is_percent:
                continue

            if is_percent:
                answer = value
                if "outperform" in sent.lower() and "by" in sent.lower():
                    stem = ("According to the document, by what margin does the "
                            "proposed model outperform the baselines?")
                else:
                    stem = "According to the document, what percentage is reported?"
                pool = [v for v in numeric_pool if "%" in v]
                pool += _numeric_variants(value, unit)
                distractors = _pick_distractors(
                    answer, pool, 3, max_words=6, sentence_mode=False)
            else:
                answer = f"{value} {unit}".strip()
                prefix = sent[:m.start()]
                subject_match = re.search(
                    r"(?P<subj>[A-Z][\w-]*(?:\s+[A-Za-z][\w-]*){0,5})\s+"
                    r"(?:contains?|includes?|has|have|comprises?)\s+"
                    r"(?:more\s+than\s+|approximately\s+|about\s+|over\s+)?$",
                    prefix,
                )
                if subject_match:
                    subject = _clean(subject_match.group("subj"))
                    stem = (f"According to the document, how many {unit} does "
                            f"{subject} contain?")
                else:
                    named_subject = re.search(
                        r"(?P<subj>(?:[Tt]he\s+)?[A-Z][\w-]*"
                        r"(?:\s+[A-Za-z][\w-]*){0,3}\s+"
                        r"(?:dataset|model|system|corpus|approach|method))\s*,",
                        prefix,
                    )
                    if named_subject:
                        subject = _clean(named_subject.group("subj"))
                        stem = (f"According to the document, how many {unit} does "
                                f"{subject} contain?")
                    else:
                        stem = (f"According to the document, how many {unit} are "
                                f"mentioned?")
                pool = [
                    v for v in numeric_pool
                    if "%" not in v and v != answer and len(v.split()) >= 2
                ]
                pool += _numeric_variants(value, unit)
                distractors = _pick_distractors(
                    answer, pool, 3, max_words=6, sentence_mode=False)

            if len(distractors) < 3:
                continue
            return _q(stem, answer, distractors[:3], "numeric", sent)
    return None


def gen_statement(sentences, terms, vocabulary, rotate):
    """"Which statement about the document is correct?"

    Built by taking a real sentence as the true statement and mutating one
    concrete term in three fakes, so exactly one option can be supported by the
    text.
    """
    replaceable = [t for t in terms if _nounish_term(t, max_words=5)]
    for sent in sentences:
        words = sent.split()
        if len(words) < 8:
            continue
        sent_low = sent.lower()
        targets = []
        for term in replaceable:
            pos = sent_low.find(term.lower())
            if pos < 0:
                continue
            if pos > max(20, len(sent) * 0.72):
                continue
            targets.append((pos, term))
        if not targets:
            continue
        targets.sort(key=lambda item: (item[0], -len(item[1])))
        target = targets[0][1]
        if _normalize_option(target) in _GENERIC_SINGLE_TERMS and " " not in target:
            continue

        term_pool = [
            t for t in replaceable
            if _normalize_option(t) != _normalize_option(target)
            and _normalize_option(t) not in _normalize_option(target)
            and _normalize_option(target) not in _normalize_option(t)
        ]
        if target[:1].isupper():
            term_pool = [t for t in term_pool if t[:1].isupper()]
        term_pool.sort(
            key=lambda t: (t[:1].isupper(), len(t.split()) > 1, len(t)),
            reverse=True,
        )
        fakes = []
        for replacement in term_pool:
            mutated = re.sub(
                re.escape(target), replacement, sent, count=1, flags=re.IGNORECASE)
            if mutated == sent:
                continue
            if not _is_complete_sentence(mutated):
                continue
            if not _plausible_option(mutated, max_words=45):
                continue
            # The substitution must be visible near the start; otherwise all
            # four options look identical on screen.
            if _normalize_option(mutated[:80]) == _normalize_option(sent[:80]):
                continue
            if any(_normalize_option(mutated) == _normalize_option(f) for f in fakes):
                continue
            fakes.append(mutated)
            if len(fakes) == 3:
                break
        if len(fakes) < 3:
            continue
        return _q(
            "Which of the following statements is supported by the document?",
            sent, fakes[:3], "statement", sent)
    return None


_GENERATORS = (
    gen_statement,
    gen_numeric,
    gen_definition,
    gen_purpose,
    gen_cause,
)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _finalize(raw: dict, rotate: int) -> dict:
    """Turn a raw generator result into the app's question shape."""
    question = _clean(raw.get("question"))
    answer_text = _display_option(raw.get("answer_text"))
    distractors = [_display_option(d) for d in (raw.get("distractors") or [])]

    if not question or not answer_text:
        return None
    if "____" in question or "___?" in question:
        return None
    if not question.endswith("?"):
        question += "?"

    options = distractors[:3] + [answer_text]
    if len(options) < 4:
        return None
    if len({_normalize_option(o) for o in options}) < 4:
        return None
    options, letter = _shuffle_with_answer(options, answer_text, rotate)
    if not letter:
        return None
    return {
        "question": question,
        "options": options,
        "answer": letter,
        "type": raw.get("type") or "statement",
        "complete": True,
    }


def build_mcq_set(text: str, count: int = 5, skip_stems=None, max_per_type: int = 1) -> list:
    """Build up to `count` varied questions from `text`.

    Generators are run in a fixed rotation and each takes the first sentence
    pattern it can use, so successive questions come from different parts of the
    document and different cognitive levels. `count` above the number of
    distinct patterns available simply returns fewer questions rather than
    repeating one.

    `skip_stems` holds question stems already used, and `max_per_type` caps how
    many questions one cognitive level may contribute, so a caller can ask for a
    wider set of a document it has partly mined already.
    """
    text = (text or "").strip()
    if not text:
        return []

    sentences = [
        s for s in sentences_of(text)
        if _is_complete_sentence(s)
    ]
    # Normalised text can repeat a sentence in a running header or caption.
    deduped = []
    seen_sentences = set()
    for sent in sentences:
        key = _normalize_option(sent)
        if key and key not in seen_sentences:
            seen_sentences.add(key)
            deduped.append(sent)
    sentences = deduped
    if len(sentences) < 2:
        return []
    # Build the vocabulary from the sentences that survived the completeness
    # gate. Using the raw text let footer words ("Proceedings") become options
    # even though no quiz question could ever be answered from them.
    terms = _key_terms(" ".join(sentences))
    vocabulary = {t.lower() for t in terms}

    built = []
    seen_stems = {_normalize_option(s) for s in (skip_stems or [])}
    per_type = {}
    # Rotate the starting generator so a two-question request does not always
    # return the same two types.
    order = list(_GENERATORS)
    if len(order) > 1:
        order = order[1:] + order[:1]

    def attempt(step, type_cap):
        if len(built) >= count:
            return
        gen = order[step % len(order)]
        # Each generator starts scanning at a different point in the document.
        # Without this every generator matched the first sentence it could, so a
        # five-question set was five questions about the document's title line.
        offset = (step * 3) % max(1, len(sentences))
        window = sentences[offset:] + sentences[:offset]
        try:
            raw = gen(window, terms, vocabulary, rotate=len(built))
        except Exception:
            return
        if not raw:
            return
        kind = raw.get("type") or "statement"
        if per_type.get(kind, 0) >= type_cap:
            return
        q = _finalize(raw, rotate=len(built))
        if not q or not q.get("complete"):
            return
        key = _normalize_option(q["question"])
        if key in seen_stems:
            return
        seen_stems.add(key)
        per_type[kind] = per_type.get(kind, 0) + 1
        built.append(q)

    # First pass: one question per type, so a set spans as many cognitive levels
    # as the document supports. A generator that matches early must not crowd out
    # the others and turn a five-question set into five variations of one idea.
    for step in range(max(count, 1) * 3):
        if len(built) >= count:
            break
        attempt(step, max_per_type)

    # Second pass: allow another question per type only if the document was too
    # thin to fill the request.
    for step in range(max(count, 1) * 3):
        if len(built) >= count:
            break
        attempt(step, max_per_type + 1)

    return built
